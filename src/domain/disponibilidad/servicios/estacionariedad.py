"""src/domain/disponibilidad/servicios/estacionariedad.py — Diagnóstico de estacionariedad temporal para modas de potencia."""

import itertools
from collections.abc import Callable
from typing import Any

from src.domain.disponibilidad.value_objects import DiagnosticoEstacionariedad
from src.domain.telemetria.value_objects import LecturaPotenciaTemporal


def evaluar_estacionariedad(
    lecturas: list[LecturaPotenciaTemporal],
    analizar_fn: Callable[..., Any],
    num_subventanas: int | None = None,
    num_bins: int | None = None,
    min_lecturas: int = 20,
    num_subventanas_default: int = 4,
    deriva_maxima_relativa: float = 0.20,
    epsilon_minimo_w: float = 0.01,
) -> DiagnosticoEstacionariedad:
    """Verifica que las modas se sostengan a lo largo de la ventana analizada."""
    tramos = num_subventanas or num_subventanas_default
    if len(lecturas) < min_lecturas * tramos or tramos < 2:
        return DiagnosticoEstacionariedad(tramos, None, None, True)

    tamano = len(lecturas) // tramos
    modas_por_tramo: list[list[float]] = []
    for t in range(tramos):
        fin = len(lecturas) if t == tramos - 1 else (t + 1) * tamano
        potencias = [lectura.potencia_w for lectura in lecturas[t * tamano : fin]]
        segmentacion = analizar_fn(potencias, num_bins=num_bins, con_barrido=False)
        modas_por_tramo.append([r.potencia_tipica_w for r in segmentacion.regimenes])

    deriva_relativa = 0.0
    deriva_w = 0.0
    for actuales, siguientes in itertools.pairwise(modas_por_tramo):
        for moda in actuales:
            if not siguientes:
                continue
            vecina = min(siguientes, key=lambda m: abs(m - moda))
            diferencia = abs(vecina - moda)
            referencia = max(abs(moda), epsilon_minimo_w)
            if diferencia / referencia > deriva_relativa:
                deriva_relativa = diferencia / referencia
                deriva_w = diferencia

    return DiagnosticoEstacionariedad(
        num_subventanas=tramos,
        desplazamiento_maximo_relativo=round(deriva_relativa, 4),
        desplazamiento_maximo_w=round(deriva_w, 4),
        es_estacionario=deriva_relativa <= deriva_maxima_relativa,
    )
