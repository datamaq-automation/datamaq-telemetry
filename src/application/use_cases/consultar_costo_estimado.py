"""src/application/use_cases/consultar_costo_estimado.py — Costo estimado del período en curso."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from src.application.dtos.sge_dto import CostoEstimadoResponseDTO
from src.application.use_cases.agregacion_dispositivos import (
    calcular_demanda_cuartohoraria,
    calcular_resumen,
)
from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.domain.sge.entities import FacturaDistribuidora
from src.domain.telemetria.entities import NodoUnifilar
from src.domain.telemetria.exceptions import PlantaNoEncontradaError
from src.domain.telemetria.ports import RepositorioOrganizacionesPort, RepositorioTelemetriaPort
from src.domain.telemetria.servicios.arbol_unifilar import ArbolUnifilarService
from src.domain.telemetria.value_objects import EsquemaPotencia, TipoNodoUnifilar

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

        facturas = self._repo_org.obtener_facturas_planta(planta_id)
        facturas_energia = [f for f in facturas if f.tipo_dato == "energia"]
        factura_energia = facturas_energia[0] if facturas_energia else None
        valor_kwh = (
            factura_energia.valor_energia_integral_ars_kwh
            if factura_energia and factura_energia.valor_energia_integral_ars_kwh is not None
            else (factura_energia.valor_energia_ars_kwh_promedio if factura_energia else None)
        )

        costo_energia_ars = (
            round(kwh_consumido_ahora * valor_kwh, 2)
            if kwh_consumido_ahora is not None and valor_kwh is not None
            else None
        )

        costo_potencia_ars, motivo_potencia = self._calcular_costo_potencia(
            planta_id, nodo_id, dispositivos_ids, facturas
        )

        habilitado, motivo_no_disponible = self._habilitacion_costo(
            self._repo_org.obtener_nodos_unifilar(planta_id), facturas
        )

        return CostoEstimadoResponseDTO(
            planta_id=planta_id,
            periodo_actual=datetime.now(ZONA_FACTURACION).strftime("%Y-%m"),
            kwh_consumido_periodo_actual=kwh_consumido_ahora,
            valor_energia_ars_kwh_promedio=valor_kwh,
            # Con el costo oculto no se publica ningún importe, ni siquiera el parcial de energía.
            costo_energia_ars=costo_energia_ars if habilitado else None,
            periodo_factura_origen=factura_energia.periodo if factura_energia else None,
            aviso_tarifa_desactualizada=self._tarifa_desactualizada(
                factura_energia.periodo if factura_energia else None
            ),
            costo_potencia_ars=costo_potencia_ars if habilitado else None,
            motivo_potencia_sin_dato=motivo_potencia,
            costo_estimado_habilitado=habilitado,
            motivo_costo_no_disponible=motivo_no_disponible,
        )

    @staticmethod
    def _habilitacion_costo(nodos: list[NodoUnifilar], facturas: list[FacturaDistribuidora]) -> tuple[bool, str | None]:
        """Capacidad única queda oculta: M-2 todavía no está integrada en este caso de uso, y sin facturas de potencia
        verificadas no hay de dónde tomar precios ni demanda. Por esquema por franja no cambia nada."""
        if not any(n.esquema_potencia is EsquemaPotencia.CAPACIDAD_UNICA for n in nodos):
            return True, None
        if not any(f.tipo_dato == "potencia" for f in facturas):
            return False, "sin liquidaciones verificadas para esta planta"
        return False, "estructura tarifaria en revisión"

    def _calcular_costo_potencia(
        self,
        planta_id: str,
        nodo_id: str | None,
        dispositivos_ids: list[str],
        facturas: list[FacturaDistribuidora],
    ) -> tuple[float | None, str | None]:
        facturas_potencia = [f for f in facturas if f.tipo_dato == "potencia" or f.importe_potencia_ars is not None]
        if not facturas_potencia:
            return None, "demanda_maxima_no_disponible"

        factura_potencia = facturas_potencia[0]
        tarifa_potencia = factura_potencia.valor_potencia_ars_kw_promedio
        if tarifa_potencia is None:
            return None, "demanda_maxima_no_disponible"

        if not dispositivos_ids:
            return None, "demanda_maxima_no_disponible"

        nodos = self._repo_org.obtener_nodos_unifilar(planta_id)
        nodo_acometida = next((n for n in nodos if n.tipo == TipoNodoUnifilar.ACOMETIDA), None) or (
            next((n for n in nodos if n.id == nodo_id), None) if nodo_id else None
        )

        pot_contratada_punta = (
            (nodo_acometida.potencia_contratada_punta_kw if nodo_acometida else None)
            or factura_potencia.potencia_contratada_punta_kw
            or 0.0
        )
        pot_contratada_fp = (
            (nodo_acometida.potencia_contratada_fuera_punta_kw if nodo_acometida else None)
            or factura_potencia.potencia_contratada_fuera_punta_kw
            or 0.0
        )

        demanda_curso = calcular_demanda_cuartohoraria(
            dispositivos_ids=dispositivos_ids,
            consultar_telemetria=self._consultar_telemetria,
        )

        if (
            demanda_curso.potencia_adquirida_punta_kw is None
            and demanda_curso.potencia_adquirida_fuera_punta_kw is None
        ):
            return None, "demanda_maxima_no_disponible"

        adquirida_punta = demanda_curso.potencia_adquirida_punta_kw or 0.0
        adquirida_fp = demanda_curso.potencia_adquirida_fuera_punta_kw or 0.0

        cargo_base = (pot_contratada_punta + pot_contratada_fp) * tarifa_potencia
        exceso_punta = max(0.0, adquirida_punta - pot_contratada_punta)
        exceso_fp = max(0.0, adquirida_fp - pot_contratada_fp)
        costo_exceso = (exceso_punta + exceso_fp) * tarifa_potencia

        costo_potencia_total = round(cargo_base + costo_exceso, 2)
        return costo_potencia_total, None

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
