"""Estimación de densidad y binarización logarítmica para potencias de máquinas."""

import itertools
import math


def percentil(ordenados: list[float], fraccion: float) -> float:
    if not ordenados:
        return 0.0
    indice = int(fraccion * (len(ordenados) - 1))
    return ordenados[min(max(indice, 0), len(ordenados) - 1)]


def estimar_epsilon(
    lecturas_w: list[float],
    piso_resolucion_w: float | None = None,
    decadas_maximas: float = 5.0,
    epsilon_minimo_w: float = 0.01,
) -> float:
    """Piso para `log(P + eps)`.

    Si el medidor declara su resolución, se usa. Si no, se estima el cuanto de
    cuantización del ADC/firmware como un percentil bajo de los saltos entre valores
    distintos consecutivos, y se acota para no exceder `decadas_maximas` de rango.
    """
    positivas = [v for v in lecturas_w if v > 0.0]
    maximo = max(positivas) if positivas else 0.0
    piso_por_rango = maximo / (10.0**decadas_maximas)

    if piso_resolucion_w is not None and piso_resolucion_w > 0.0:
        return max(piso_resolucion_w, epsilon_minimo_w)

    distintos = sorted(set(positivas))
    saltos = sorted(b - a for a, b in itertools.pairwise(distintos) if b > a)
    cuanto = percentil(saltos, 0.10) if saltos else 0.0

    return max(cuanto, piso_por_rango, epsilon_minimo_w)


def construir_bins_log(
    lecturas_w: list[float],
    num_bins: int,
    eps_w: float,
) -> tuple[list[float], list[int]]:
    """Bins de ancho fijo en escala log; bordes devueltos en watts (ancho variable).

    Devuelve `num_bins + 1` bordes: con bins de ancho variable el consumidor no puede
    reconstruir el último borde asumiendo espaciado uniforme.

    Nota: potencias <= 0 se pisan a 0.0 para la transformación logarítmica pero se conservan
    en su valor real para masa, mediana y ΔP, y se contabilizan en el diagnóstico.
    """
    transformados = [math.log(max(v, 0.0) + eps_w) for v in lecturas_w]
    minimo, maximo = min(transformados), max(transformados)

    if maximo <= minimo:
        borde = math.exp(minimo) - eps_w
        return [borde, borde], [len(lecturas_w)]

    ancho = (maximo - minimo) / num_bins
    conteos = [0] * num_bins
    for valor in transformados:
        indice = min(int((valor - minimo) / ancho), num_bins - 1)
        conteos[indice] += 1

    bordes = [math.exp(minimo + i * ancho) - eps_w for i in range(num_bins + 1)]
    return bordes, conteos


def suavizar(conteos: list[int], ventana: int = 3) -> list[float]:
    if ventana < 2 or len(conteos) < ventana:
        return [float(c) for c in conteos]
    radio = ventana // 2
    suavizados = []
    for i in range(len(conteos)):
        desde = max(0, i - radio)
        hasta = min(len(conteos), i + radio + 1)
        valores_ventana = conteos[desde:hasta]
        suavizados.append(sum(valores_ventana) / len(valores_ventana))
    return suavizados


def detectar_picos_locales(suavizados: list[float]) -> list[int]:
    """Detecta índices de máximos locales en una curva suavizada."""
    picos: list[int] = []
    for i in range(1, len(suavizados) - 1):
        if suavizados[i] > suavizados[i - 1] and suavizados[i] >= suavizados[i + 1]:
            picos.append(i)
    return picos
