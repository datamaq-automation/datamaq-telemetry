"""src/domain/telemetria/servicios/calculador_coherencia.py — Cálculo de coherencia fasorial."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CoherenciaDispositivo:
    """Resumen de coherencia fasorial de un dispositivo."""

    dispositivo_id: str
    error_promedio_pct: float
    vigencia_dias: int


class CalculadorCoherenciaService:
    """Cálculos de coherencia fasorial (Capa 2: Gauntlet Diario)."""

    @staticmethod
    def calcular_coherencia_promedio(error_s_list: list[float]) -> float:
        """Media aritmética de errores de coherencia.

        Args:
            error_s_list: Lista de error_s en % de cada registro instantáneo.

        Returns:
            Promedio de errores. 0.0 si lista vacía.
        """
        if not error_s_list:
            return 0.0
        return sum(error_s_list) / len(error_s_list)

    @staticmethod
    def evaluar_degradacion(promedio_hoy: float, baseline_7d: float) -> tuple[bool, float]:
        """Evalúa si hay degradación significativa vs histórico.

        Args:
            promedio_hoy: Error % promedio de las últimas 24h.
            baseline_7d: Error % promedio de los 7 días anteriores.

        Returns:
            (está_degradado, pct_cambio) donde:
            - está_degradado: True si cambio > +20%
            - pct_cambio: Porcentaje de cambio relativo (ej. +50.0, -10.0)
        """
        if baseline_7d == 0:
            if promedio_hoy > 0:
                return (True, 100.0)
            return (False, 0.0)

        pct_cambio = ((promedio_hoy - baseline_7d) / baseline_7d) * 100.0
        está_degradado = pct_cambio > 20.0

        return (está_degradado, pct_cambio)
