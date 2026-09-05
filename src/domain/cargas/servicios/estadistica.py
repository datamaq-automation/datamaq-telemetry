"""Estadística robusta compartida por los servicios de desagregación de cargas.

Robusta y no clásica a propósito: una serie de potencia doméstica está llena de
excursiones únicas (un arranque de motor, una puerta de heladera abierta) que
desplazarían una media o un desvío estándar sin describir el comportamiento típico.
Mediana y MAD son el mismo criterio que ya usa `SegmentadorRegimenesService`.
"""

import itertools
import statistics
from datetime import datetime


def percentil(valores: list[float], fraccion: float) -> float | None:
    """Percentil por índice sobre la lista ordenada. `None` si no hay datos."""
    if not valores:
        return None
    ordenados = sorted(valores)
    indice = int(fraccion * (len(ordenados) - 1))
    return ordenados[min(max(indice, 0), len(ordenados) - 1)]


def mediana(valores: list[float]) -> float | None:
    return statistics.median(valores) if valores else None


def desviacion_absoluta_mediana(valores: list[float]) -> float | None:
    """MAD: mediana de las distancias a la mediana. Necesita al menos dos valores."""
    if len(valores) < 2:
        return None
    centro = statistics.median(valores)
    return statistics.median([abs(v - centro) for v in valores])


def cadencia_mediana_segundos(momentos: list[datetime]) -> float | None:
    """Δt mediano de la serie.

    Se infiere, no se asume: el mismo medidor alterna 300 s en modo estándar y 1-5 s
    en ráfaga, y todo umbral temporal de los servicios se expresa en múltiplos de esto.
    """
    deltas = [(b - a).total_seconds() for a, b in itertools.pairwise(momentos) if (b - a).total_seconds() > 0]
    return statistics.median(deltas) if deltas else None


def dispersion_relativa(valores: list[float]) -> float | None:
    """MAD / mediana. Adimensional, para comparar regularidad entre cargas de distinta escala."""
    centro = mediana(valores)
    mad = desviacion_absoluta_mediana(valores)
    if centro is None or mad is None or centro <= 0:
        return None
    return mad / centro
