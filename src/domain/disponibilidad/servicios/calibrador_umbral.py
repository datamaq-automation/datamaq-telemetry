"""Calibración de umbral marcha/parada a partir de segmentación modal (k=2)."""

from src.domain.disponibilidad.servicios.segmentador_regimenes import (
    SegmentadorRegimenesService,
)


class CalibradorUmbralService:
    """Calibra el umbral marcha/parada a partir del histograma de potencia de una máquina.

    Es el caso k=2 de `SegmentadorRegimenesService`: el umbral es la antimoda que separa
    el régimen de menor potencia (parada/standby) del resto. Toda la matemática vive en el
    segmentador; acá solo queda la traducción al vocabulario binario de disponibilidad.

    Devuelve `None` cuando la distribución no sostiene más de un régimen: no se fuerza un
    umbral sobre datos que no lo respaldan. En ese caso corresponde calibración manual
    (`PATCH /maquinas/{id}` con `umbral_marcha_w` explícito).
    """

    MIN_LECTURAS = SegmentadorRegimenesService.MIN_LECTURAS

    @classmethod
    def construir_histograma(
        cls, lecturas_w: list[float], num_bins: int | None = None
    ) -> tuple[list[float], list[int]]:
        """Bordes de bins y frecuencias, vacíos si no hay suficientes lecturas."""
        segmentacion = SegmentadorRegimenesService.analizar(lecturas_w, num_bins, con_barrido=False)
        return segmentacion.bordes_bins_w, segmentacion.frecuencias

    @classmethod
    def calcular_umbral(cls, lecturas_w: list[float], num_bins: int | None = None) -> float | None:
        return SegmentadorRegimenesService.analizar(lecturas_w, num_bins, con_barrido=False).umbral_marcha_sugerido_w
