"""Análisis temporal, cadencia y tasas de variación (|ΔP|/Δt) para clasificar regímenes."""

import bisect
import itertools
import statistics
from dataclasses import replace

from src.domain.disponibilidad.value_objects import NaturalezaRegimen, RegimenOperacion
from src.domain.telemetria.value_objects import LecturaPotenciaTemporal


def estimar_cadencia_nominal(lecturas: list[LecturaPotenciaTemporal]) -> float | None:
    """Mediana de los Δt en segundos. Se infiere de la serie, no se hardcodea."""
    deltas = [
        (b.momento - a.momento).total_seconds()
        for a, b in itertools.pairwise(lecturas)
        if (b.momento - a.momento).total_seconds() > 0
    ]
    return statistics.median(deltas) if deltas else None


def tasas_de_variacion(
    lecturas: list[LecturaPotenciaTemporal],
    cadencia_s: float,
    factor_hueco: float = 3.0,
) -> list[tuple[float, float]]:
    """Calcula `[(potencia_media, |ΔP|/Δt), ...]` descartando huecos de datos."""
    limite = factor_hueco * cadencia_s
    tasas: list[tuple[float, float]] = []
    for anterior, actual in itertools.pairwise(lecturas):
        delta_t = (actual.momento - anterior.momento).total_seconds()
        if delta_t <= 0 or delta_t > limite:
            continue
        potencia_media = (anterior.potencia_w + actual.potencia_w) / 2.0
        tasas.append((potencia_media, abs(actual.potencia_w - anterior.potencia_w) / delta_t))
    return tasas


def deltas_potencia_validos(
    lecturas: list[LecturaPotenciaTemporal],
    factor_hueco: float | None = None,
    factor_hueco_default: float = 3.0,
) -> list[tuple[float, float]]:
    cadencia = estimar_cadencia_nominal(lecturas)
    if not cadencia:
        return []
    return tasas_de_variacion(lecturas, cadencia, factor_hueco or factor_hueco_default)


def clasificar_naturaleza(
    regimenes: list[RegimenOperacion],
    tasas: list[tuple[float, float]],
    cadencia_s: float,
) -> list[RegimenOperacion]:
    """Asigna a cada régimen su |ΔP|/Δt mediano y lo marca estable o transitorio."""
    if not tasas or not regimenes:
        return regimenes

    cortes_w = [r.limite_superior_w for r in regimenes[:-1]]
    por_regimen: list[list[float]] = [[] for _ in regimenes]
    for potencia_media, tasa in tasas:
        por_regimen[bisect.bisect_right(cortes_w, potencia_media)].append(tasa)

    clasificados: list[RegimenOperacion] = []
    for regimen, propias in zip(regimenes, por_regimen, strict=True):
        if not propias:
            clasificados.append(regimen)
            continue
        tasa_regimen = statistics.median(propias)
        salto_tipico_w = tasa_regimen * cadencia_s
        ancho_banda_w = regimen.limite_superior_w - regimen.limite_inferior_w
        naturaleza = NaturalezaRegimen.TRANSITORIO if salto_tipico_w > ancho_banda_w else NaturalezaRegimen.ESTABLE
        clasificados.append(replace(regimen, variacion_mediana_w_s=round(tasa_regimen, 6), naturaleza=naturaleza))
    return clasificados
