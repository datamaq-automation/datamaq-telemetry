"""src/domain/produccion/servicios/calculador_enpi.py — Servicio de dominio para cálculo de EnPI y SEC (ISO 50001/50006)."""

from datetime import datetime

from src.domain.produccion.value_objects import (
    LecturaVariableProceso,
    MetricasConsumoEspecifico,
    TipoVariableProceso,
)


class CalculadorEnPIService:
    """Calcula Indicadores de Desempeño Energético y Consumos Específicos según producción."""

    @staticmethod
    def calcular_sec(energia_kwh: float, delta_unidades: float) -> float | None:
        """Calcula el Consumo Específico de Energía (SEC).

        Retorna None si las unidades son menores o iguales a cero para evitar división nula.
        """
        if delta_unidades <= 0.0 or energia_kwh < 0.0:
            return None
        return round(energia_kwh / delta_unidades, 6)

    @classmethod
    def calcular_metricas(
        cls,
        periodo_inicio: datetime,
        periodo_fin: datetime,
        energia_kwh: float,
        lecturas_proceso: list[LecturaVariableProceso],
        tipo: TipoVariableProceso,
    ) -> MetricasConsumoEspecifico:
        """Genera métricas EnPI agregadas cruzando energía y lecturas de sensórica de proceso."""
        unidades = sum(lectura.delta_valor for lectura in lecturas_proceso if lectura.variable_tipo == tipo)
        sec = cls.calcular_sec(energia_kwh, unidades)
        return MetricasConsumoEspecifico(
            periodo_inicio=periodo_inicio,
            periodo_fin=periodo_fin,
            energia_kwh=energia_kwh,
            unidades_procesadas=unidades,
            sec_kwh_por_unidad=sec,
        )

    @staticmethod
    def discriminar_consumo_basal(
        energia_total_kwh: float,
        horas_periodo: float,
        horas_en_produccion: float,
        potencia_base_kw: float,
    ) -> tuple[float, float]:
        """Separa la energía basal (transformador/vacío) de la energía productiva neta."""
        e_base = round(potencia_base_kw * horas_periodo, 3)
        e_proceso = round(max(0.0, energia_total_kwh - e_base), 3)
        return e_base, e_proceso
