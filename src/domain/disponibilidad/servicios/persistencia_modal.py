"""src/domain/disponibilidad/servicios/persistencia_modal.py — Persistencia topológica 1-D y selección de modas para distribuciones de potencia."""

import math
from collections import Counter

from src.domain.disponibilidad.servicios.histograma_log import suavizar
from src.domain.disponibilidad.value_objects import DiagnosticoConfianzaModal


def persistencia_de_modas(alturas: list[float]) -> dict[int, tuple[float, int | None]]:
    """`{indice_de_moda: (persistencia, indice_de_la_antimoda_donde_muere)}`.

    Merge tree 1-D por union-find, barriendo de mayor a menor altura. Cada índice o
    bien nace como componente nueva (es un máximo local), o extiende una componente
    existente, o fusiona dos: en la fusión muere la componente más joven (la del
    pico más bajo), y su persistencia es cuánto hay que descender desde su pico hasta
    ese punto de unión para alcanzar un pico más alto. El máximo global nunca muere.
    """
    n = len(alturas)
    if n == 0:
        return {}

    orden = sorted(range(n), key=lambda i: (-alturas[i], i))
    padre: dict[int, int] = {}
    nacimiento: dict[int, float] = {}
    activo = [False] * n
    resultado: dict[int, tuple[float, int | None]] = {}

    def encontrar(i: int) -> int:
        raiz = i
        while padre[raiz] != raiz:
            raiz = padre[raiz]
        while padre[i] != raiz:
            padre[i], i = raiz, padre[i]
        return raiz

    for i in orden:
        activo[i] = True
        padre[i] = i
        nacimiento[i] = alturas[i]

        raices: list[int] = []
        for vecino in (i - 1, i + 1):
            if 0 <= vecino < n and activo[vecino]:
                raiz = encontrar(vecino)
                if raiz not in raices:
                    raices.append(raiz)

        if not raices:
            continue

        raices.sort(key=lambda r: (-nacimiento[r], r))
        principal = raices[0]
        for secundaria in raices[1:]:
            resultado[secundaria] = (nacimiento[secundaria] - alturas[i], i)
            padre[secundaria] = principal
        padre[i] = principal

    resultado[encontrar(orden[0])] = (math.inf, None)
    return resultado


def seleccionar_modas(suavizados: list[float], persistencia_minima_relativa: float) -> list[int]:
    """Índices de las modas que superan el corte de persistencia, ordenados por potencia."""
    if not suavizados:
        return []
    rango = max(suavizados) - min(suavizados)
    if rango <= 0.0:
        return []
    corte = persistencia_minima_relativa * rango
    persistencias = persistencia_de_modas(suavizados)
    return sorted(i for i, (persistencia, _) in persistencias.items() if persistencia >= corte)


def antimoda_entre(suavizados: list[float], izquierda: int, derecha: int) -> int:
    """Bin del valle entre dos modas; con el valle chato, su centro."""
    tramo = range(izquierda, derecha + 1)
    minimo = min(suavizados[i] for i in tramo)
    empatados = [i for i in tramo if suavizados[i] == minimo]
    return empatados[len(empatados) // 2]


def barrer_ancho_banda(
    conteos: list[int],
    persistencia_minima_relativa: float,
    ventanas_barrido: tuple[int, ...] = (1, 3, 5, 7, 9, 11, 13, 15),
    fraccion_consistencia_minima: float = 0.6,
) -> DiagnosticoConfianzaModal:
    """Cuenta modas para cada ancho de suavizado y mide qué estructura sobrevive."""
    conteos_de_modas = [
        len(seleccionar_modas(suavizar(conteos, ventana), persistencia_minima_relativa)) for ventana in ventanas_barrido
    ]
    if not conteos_de_modas:
        return DiagnosticoConfianzaModal(0, 0.0, False)

    num_estable, repeticiones = Counter(conteos_de_modas).most_common(1)[0]
    fraccion = repeticiones / len(conteos_de_modas)
    return DiagnosticoConfianzaModal(
        num_modas_estable=num_estable,
        fraccion_ventanas_consistentes=round(fraccion, 4),
        es_multimodal_confiable=num_estable >= 2 and fraccion >= fraccion_consistencia_minima,
    )
