"""src/application/use_cases/consultar_ahorros_cusum.py — Cálculo de ahorros y curva CUSUM frente a EnB (ISO 50006)."""

from datetime import datetime, timezone

from src.application.dtos.sge_dto import AhorrosCusumResponseDTO, PuntoCusumDTO
from src.domain.produccion.servicios.calculador_ahorros_iso import (
    CalculadorAhorrosIsoService,
    LineaBaseCongelada,
)
from src.domain.telemetria.exceptions import PlantaNoEncontradaError
from src.domain.telemetria.ports import RepositorioOrganizacionesPort


class LineaBaseNoEncontradaError(Exception):
    pass


class ConsultarAhorrosCusumUseCase:
    def __init__(self, repo_organizaciones: RepositorioOrganizacionesPort):
        self._repo_org = repo_organizaciones

    def ejecutar(
        self,
        planta_id: str,
        unidades_producidas: float,
        horas_periodo: float,
        energia_real_kwh: float,
        linea_base_id: str | None = None,
        historico_ahorros: list[float] | None = None,
    ) -> AhorrosCusumResponseDTO:
        planta = self._repo_org.obtener_planta_por_id(planta_id)
        if not planta:
            raise PlantaNoEncontradaError(f"Planta {planta_id} no encontrada.")

        lineas_raw = self._repo_org.obtener_lineas_base_planta(planta_id)
        if not lineas_raw:
            raise LineaBaseNoEncontradaError(
                f"No hay Líneas de Base Energética (EnB) declaradas para la planta {planta_id} en organizaciones.yml."
            )

        lb_data = None
        if linea_base_id:
            lb_data = next((lb for lb in lineas_raw if lb.get("id") == linea_base_id), None)
        else:
            lb_data = next((lb for lb in lineas_raw if lb.get("activa", True)), lineas_raw[0])

        if not lb_data:
            raise LineaBaseNoEncontradaError(f"Línea de base {linea_base_id} no encontrada.")

        enb = LineaBaseCongelada(
            id=str(lb_data["id"]),
            nombre=str(lb_data.get("nombre", "EnB")),
            sec_referencia=float(lb_data.get("sec_referencia_kwh_unidad", 0.1)),
            potencia_base_kw=float(lb_data.get("potencia_base_kw", 0.0)),
            periodo_referencia_desde=datetime.now(timezone.utc),
            periodo_referencia_hasta=datetime.now(timezone.utc),
            congelada_en=datetime.now(timezone.utc),
        )

        resultado = CalculadorAhorrosIsoService.evaluar_periodo(
            linea_base=enb,
            unidades_producidas=unidades_producidas,
            horas_periodo=horas_periodo,
            energia_real_kwh=energia_real_kwh,
        )

        ahorros_serie = historico_ahorros if historico_ahorros is not None else [resultado.ahorro_kwh]
        cusum_serie = CalculadorAhorrosIsoService.calcular_cusum(ahorros_serie)

        n_puntos = len(ahorros_serie) if len(ahorros_serie) > 0 else 1
        puntos: list[PuntoCusumDTO] = []
        for i, (a, c) in enumerate(zip(ahorros_serie, cusum_serie, strict=False), start=1):
            puntos.append(
                PuntoCusumDTO(
                    fecha=f"Punto {i}",
                    energia_real_kwh=round(energia_real_kwh / n_puntos, 2),
                    energia_esperada_kwh=round(resultado.energia_esperada_kwh / n_puntos, 2),
                    ahorro_kwh=a,
                    cusum_acumulado_kwh=c,
                )
            )

        return AhorrosCusumResponseDTO(
            planta_id=planta_id,
            linea_base_id=enb.id,
            linea_base_nombre=enb.nombre,
            ahorro_total_kwh=resultado.ahorro_kwh,
            ahorro_porcentual=resultado.ahorro_porcentual,
            es_mejora=resultado.es_mejora,
            detalle=resultado.detalle,
            puntos_cusum=puntos,
        )
