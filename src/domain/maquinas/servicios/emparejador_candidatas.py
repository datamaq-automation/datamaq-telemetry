"""src/domain/maquinas/servicios/emparejador_candidatas.py — Emparejador puro de candidatas."""

from src.domain.maquinas.entities import Máquina
from src.domain.maquinas.value_objects import MáquinaInferida


def emparejar(candidata: MáquinaInferida, cargas: list[Máquina], tolerancia_relativa: float = 0.15) -> Máquina | None:
    """Empareja candidata con la carga del catálogo de potencia más cercana.

    Máquina válida: potencia_esperada_w no None.
    Tolerancia: max(tolerancia_relativa * candidata.potencia_w, 2 * candidata.dispersion_w).
    Empate: la de menor diferencia, luego menor id.

    Args:
        candidata: carga inferida por el descubridor
        cargas: catálogo completo del dispositivo
        tolerancia_relativa: factor relativo de tolerancia (default 0.15 = 15%)

    Returns:
        Máquina emparejada o None si no hay candidata dentro de tolerancia.
    """
    # Filtrar cargas con potencia esperada definida
    cargas_validas = [c for c in cargas if c.potencia_esperada_w is not None]

    if not cargas_validas:
        return None

    # Calcular tolerancia
    tolerancia_relativa_w = tolerancia_relativa * candidata.potencia_w
    tolerancia_dispersion_w = 2 * candidata.dispersion_w
    tolerancia = max(tolerancia_relativa_w, tolerancia_dispersion_w)

    # Encontrar la más cercana
    mejores: list[tuple[float, str, Máquina]] = []
    for carga in cargas_validas:
        potencia_esperada = carga.potencia_esperada_w
        assert potencia_esperada is not None
        diferencia = abs(candidata.potencia_w - potencia_esperada)

        if diferencia <= tolerancia:
            mejores.append((diferencia, carga.id, carga))

    if not mejores:
        return None

    # Ordenar por diferencia (ascendente) y luego por id (ascendente)
    mejores.sort(key=lambda x: (x[0], x[1]))
    return mejores[0][2]
