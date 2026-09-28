"""src/application/use_cases/consultar_costo_estimado.py — Costo estimado del período en curso."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from src.application.dtos.sge_dto import CostoEstimadoResponseDTO
from src.application.use_cases.agregacion_dispositivos import calcular_resumen
from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.domain.telemetria.exceptions import PlantaNoEncontradaError
from src.domain.telemetria.ports import RepositorioOrganizacionesPort, RepositorioTelemetriaPort
from src.domain.telemetria.servicios.arbol_unifilar import ArbolUnifilarService
from src.domain.telemetria.value_objects import TipoNodoUnifilar

# Días desde el cierre del período de la factura de origen a partir de los cuales se avisa que la
# tarifa pudo cambiar (D4 de la decisión del dueño): un ciclo de facturación son ~30 días, con
# margen para el desfasaje habitual entre cierre de período y emisión/carga de la factura.
DIAS_AVISO_TARIFA_DESACTUALIZADA = 35

ZONA_FACTURACION = ZoneInfo("America/Argentina/Buenos_Aires")

# Ventana de consulta para la agregación mensual: alcanza con el mes en curso y el anterior
# (el delta del mes en curso se calcula contra el cierre del anterior).
DIAS_VENTANA_ENERGIA_MENSUAL = 60


class ConsultarCostoEstimadoUseCase:
    """Costo estimado en pesos del período de facturación en curso de una planta.

    Componente de energía: kWh consumidos hasta ahora (datos en vivo) x `$/kWh` promedio de la
    última factura de energía real de la planta (D1-D5,
    `decisions/2026-09-27_costo-estimado-periodo-en-curso.md`). Componente de potencia: "s/d"
    explícito — requiere tracking de demanda máxima del período en curso, que todavía no existe.
    """

    def __init__(
        self,
        repo_organizaciones: RepositorioOrganizacionesPort,
        repo_telemetria: RepositorioTelemetriaPort,
        consultar_telemetria: ConsultarTelemetriaUseCase,
    ):
        self._repo_org = repo_organizaciones
        self._repo_telemetria = repo_telemetria
        self._consultar_telemetria = consultar_telemetria

    def ejecutar(self, planta_id: str, nodo_id: str | None = None) -> CostoEstimadoResponseDTO:
        planta = self._repo_org.obtener_planta_por_id(planta_id)
        if not planta:
            raise PlantaNoEncontradaError(f"Planta {planta_id} no encontrada.")

        dispositivos_ids = self._resolver_dispositivos_frontera(planta_id, nodo_id)
        kwh_consumido_ahora = self._kwh_periodo_en_curso(dispositivos_ids)

        facturas_energia = [f for f in self._repo_org.obtener_facturas_planta(planta_id) if f.tipo_dato == "energia"]
        factura = facturas_energia[0] if facturas_energia else None
        valor_kwh = factura.valor_energia_ars_kwh_promedio if factura else None

        costo_energia_ars = (
            round(kwh_consumido_ahora * valor_kwh, 2)
            if kwh_consumido_ahora is not None and valor_kwh is not None
            else None
        )

        return CostoEstimadoResponseDTO(
            planta_id=planta_id,
            periodo_actual=datetime.now(ZONA_FACTURACION).strftime("%Y-%m"),
            kwh_consumido_periodo_actual=kwh_consumido_ahora,
            valor_energia_ars_kwh_promedio=valor_kwh,
            costo_energia_ars=costo_energia_ars,
            periodo_factura_origen=factura.periodo if factura else None,
            aviso_tarifa_desactualizada=self._tarifa_desactualizada(factura.periodo if factura else None),
            costo_potencia_ars=None,
            motivo_potencia_sin_dato="demanda_maxima_no_disponible",
        )

    def _resolver_dispositivos_frontera(self, planta_id: str, nodo_id: str | None) -> list[str]:
        nodos = self._repo_org.obtener_nodos_unifilar(planta_id)
        if not nodos:
            return []
        arbol = ArbolUnifilarService(nodos)
        if nodo_id:
            nodo = arbol.obtener(nodo_id)
        else:
            nodo = next(
                (n for n in nodos if n.tipo in (TipoNodoUnifilar.TGBT, TipoNodoUnifilar.TRANSFORMADOR)),
                None,
            ) or next((n for n in nodos if n.parent_id is None), None)
        return arbol.medidores_frontera(nodo.id) if nodo else []

    def _kwh_periodo_en_curso(self, dispositivos_ids: list[str]) -> float | None:
        if not dispositivos_ids:
            return None
        _, energia_sumada = calcular_resumen(
            dispositivos_ids=dispositivos_ids,
            repo_telemetria=self._repo_telemetria,
            consultar_telemetria=self._consultar_telemetria,
            granularidad="month",
            zona="America/Argentina/Buenos_Aires",
            dias=DIAS_VENTANA_ENERGIA_MENSUAL,
        )
        inicio_mes_actual = datetime.now(ZONA_FACTURACION).date().replace(day=1)
        entrada = next((e for e in energia_sumada if e.periodo == inicio_mes_actual), None)
        return entrada.energia_activa_neta_kwh if entrada else None

    def _tarifa_desactualizada(self, periodo_factura: str | None) -> bool:
        if periodo_factura is None:
            return False
        anio, mes = (int(parte) for parte in periodo_factura.split("-"))
        anio_siguiente, mes_siguiente = (anio + 1, 1) if mes == 12 else (anio, mes + 1)
        fin_periodo = datetime(anio_siguiente, mes_siguiente, 1, tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - fin_periodo).days > DIAS_AVISO_TARIFA_DESACTUALIZADA
