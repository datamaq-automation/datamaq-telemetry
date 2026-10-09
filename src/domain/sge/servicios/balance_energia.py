"""src/domain/sge/servicios/balance_energia.py — Balance de masa y energía en TGBT para revisión energética (ISO 50001 §6.3)."""

from dataclasses import dataclass
from enum import Enum


class EstadoBalanceEnergia(str, Enum):
    CONCILIADO_NORMAL = "CONCILIADO_NORMAL"
    PERDIDAS_ELEVADAS = "PERDIDAS_ELEVADAS"
    PERDIDAS_ELEVADAS_POR_ARMONICOS = "PERDIDAS_ELEVADAS_POR_ARMONICOS"
    DESBALANCE_CRITICO = "DESBALANCE_CRITICO"
    SOBRECONTEO = "SOBRECONTEO"


@dataclass(frozen=True)
class ResultadoBalanceEnergia:
    energia_padre_kwh: float
    energia_hijos_sumada_kwh: float
    residual_kwh: float
    residual_porcentual: float
    estado: EstadoBalanceEnergia
    es_auditable_iso50001: bool
    detalle: str
    thd_i_promedio_pct: float | None = None


class BalanceEnergiaService:
    """Verifica la conciliación de energía entre el nodo de cabecera (TGBT/Trafo) y sus subtableros/cargas."""

    TOLERANCIA_PERDIDAS_MAXIMA_PCT = 0.04
    TOLERANCIA_PERDIDAS_ELEVADAS_PCT = 0.10
    # Umbral interno, sin respaldo normativo documentado (ver specs/thd-visualizacion-calidad-energia.md).
    UMBRAL_THD_I_CRITICO_PCT = 15.0

    @classmethod
    def _clasificar_estado_balance(
        cls,
        residual_pct: float,
        residual: float,
        suma_hijos: float,
        energia_padre_kwh: float,
        thd_i_promedio_pct: float | None,
    ) -> tuple[EstadoBalanceEnergia, bool, str]:
        if residual < 0.0:
            return (
                EstadoBalanceEnergia.SOBRECONTEO,
                False,
                f"Sobreconteo: los circuitos hijos ({suma_hijos:.1f} kWh) superan a la cabecera ({energia_padre_kwh:.1f} kWh). Revisar TI.",
            )
        if residual_pct <= cls.TOLERANCIA_PERDIDAS_MAXIMA_PCT:
            return (
                EstadoBalanceEnergia.CONCILIADO_NORMAL,
                True,
                f"Balance normal: residual de {residual:.1f} kWh ({residual_pct:.1%}) dentro de pérdidas técnicas admisibles de trafo/cable.",
            )
        if residual_pct <= cls.TOLERANCIA_PERDIDAS_ELEVADAS_PCT:
            if thd_i_promedio_pct is not None and thd_i_promedio_pct > cls.UMBRAL_THD_I_CRITICO_PCT:
                return (
                    EstadoBalanceEnergia.PERDIDAS_ELEVADAS_POR_ARMONICOS,
                    True,
                    (
                        f"Pérdidas elevadas ({residual_pct:.1%}) justificadas por distorsión armónica en corriente "
                        f"(THD_I {thd_i_promedio_pct:.1f}% > {cls.UMBRAL_THD_I_CRITICO_PCT}%, umbral interno) "
                        "que eleva pérdidas térmicas Joule I^2*R en trafo/cables."
                    ),
                )
            return (
                EstadoBalanceEnergia.PERDIDAS_ELEVADAS,
                False,
                f"Pérdidas elevadas ({residual_pct:.1%}): posible sobrecalentamiento de líneas, fuga o cargas menores sin medir.",
            )
        return (
            EstadoBalanceEnergia.DESBALANCE_CRITICO,
            False,
            f"Desbalance crítico ({residual_pct:.1%}): residual de {residual:.1f} kWh no justificado. Alerta de consumo no inventariado.",
        )

    @classmethod
    def evaluar_balance(
        cls,
        energia_padre_kwh: float,
        energias_hijos_kwh: list[float],
        thd_i_promedio_pct: float | None = None,
    ) -> ResultadoBalanceEnergia:
        if energia_padre_kwh <= 0.0:
            return ResultadoBalanceEnergia(
                energia_padre_kwh=0.0,
                energia_hijos_sumada_kwh=0.0,
                residual_kwh=0.0,
                residual_porcentual=0.0,
                estado=EstadoBalanceEnergia.CONCILIADO_NORMAL,
                es_auditable_iso50001=True,
                detalle="Energía de cabecera nula o no registrada.",
                thd_i_promedio_pct=thd_i_promedio_pct,
            )

        suma_hijos = round(sum(max(0.0, h) for h in energias_hijos_kwh), 3)
        residual = round(energia_padre_kwh - suma_hijos, 3)
        residual_pct = round(residual / energia_padre_kwh, 4)

        estado, auditable, detalle = cls._clasificar_estado_balance(
            residual_pct, residual, suma_hijos, energia_padre_kwh, thd_i_promedio_pct
        )

        return ResultadoBalanceEnergia(
            energia_padre_kwh=round(energia_padre_kwh, 3),
            energia_hijos_sumada_kwh=suma_hijos,
            residual_kwh=residual,
            residual_porcentual=residual_pct,
            estado=estado,
            es_auditable_iso50001=auditable,
            detalle=detalle,
            thd_i_promedio_pct=thd_i_promedio_pct,
        )
