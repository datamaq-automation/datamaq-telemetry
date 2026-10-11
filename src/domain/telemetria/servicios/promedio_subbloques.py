"""src/domain/telemetria/servicios/promedio_subbloques.py — valor de un bloque de demanda por sub-bloques.

Decisión 2026-10-11: el valor de cada bloque de 15 min es el promedio de los tres bloques de 5 min que lo
contienen (00-04, 05-09 y 10-14 de cada cuarto de hora, en hora local de la facturación). No es el promedio
simple de las muestras: si un sub-bloque tiene más muestras que otro, no pesa más.
"""

from collections.abc import Iterable

BLOQUE_DEMANDA_SEGUNDOS = 900
SUBBLOQUE_DEMANDA_SEGUNDOS = 300


def segundos_subbloque(intervalo_segundos: int) -> int:
    """Sub-bloque que promedia un bloque: 5 min para el bloque de 15 min; el propio bloque en otro caso."""
    return SUBBLOQUE_DEMANDA_SEGUNDOS if intervalo_segundos == BLOQUE_DEMANDA_SEGUNDOS else intervalo_segundos


def promedio_por_subbloques(muestras: Iterable[tuple[float, float]], intervalo_segundos: int) -> float | None:
    """Media de las medias de los sub-bloques que tienen muestras.

    ``muestras`` son pares ``(epoch_segundos, valor)`` de un mismo medidor y bloque. Con otro intervalo distinto
    de 15 min, el sub-bloque es el propio bloque y el resultado es la media simple.
    """
    sub = segundos_subbloque(intervalo_segundos)
    por_subbloque: dict[int, list[float]] = {}
    for epoch_s, valor in muestras:
        por_subbloque.setdefault(int(epoch_s // sub), []).append(valor)
    if not por_subbloque:
        return None
    medias = [sum(valores) / len(valores) for valores in por_subbloque.values()]
    return sum(medias) / len(medias)
