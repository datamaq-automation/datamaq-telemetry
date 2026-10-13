"""Corrección angular de TI por fase, calculada desde V, I y P.

Convención (spec ``trafo2-los-constituyentes-fases.md``, A2): ``correccion_angular_fases: "X:alfa"``
rota el fasor de potencia en -alfa. Si el ángulo bruto de una fase es φ_bruto y la corrección es alfa,
el ángulo almacenado es φ_almacenado = φ_bruto - alfa (mod 360).

Limitación: de V, I y P solo se obtiene |φ| = acos(P / (V·I)). El signo de Q no está en esos datos,
así que el ángulo queda con signo indeterminado. Este módulo enumera los candidatos compatibles con
dos configuraciones y no elige uno: esa elección requiere Q o una verificación en campo.
"""

from __future__ import annotations

import math


def normalizar_grados(angulo: float) -> float:
    """Lleva un ángulo en grados al intervalo (-180, 180]."""
    resto = angulo % 360.0
    if resto > 180.0:
        resto -= 360.0
    return resto


def magnitud_angulo_deg(v: float, i: float, p: float) -> float:
    """|φ| en grados, desde tensión, corriente y potencia activa de una fase.

    Es el arcocoseno del factor de potencia P / (V·I). No tiene signo: ver el docstring del módulo.
    """
    s = v * i
    if s <= 0:
        raise ValueError(f"S = V·I debe ser > 0 (V={v}, I={i})")
    factor_potencia = max(-1.0, min(1.0, p / s))
    return math.degrees(math.acos(factor_potencia))


def angulo_almacenado(phi_bruto: float, alpha: float) -> float:
    """Ángulo que queda en telemetría al aplicar la corrección alfa sobre un ángulo bruto."""
    return normalizar_grados(phi_bruto - alpha)


def potencia_activa_predicha(s: float, phi_bruto: float, alpha: float) -> float:
    """P = S·cos(φ_almacenado), con la corrección alfa aplicada."""
    return s * math.cos(math.radians(angulo_almacenado(phi_bruto, alpha)))


def alpha_para_objetivo(phi_bruto: float, phi_objetivo: float = 30.0) -> float:
    """Corrección alfa que lleva el ángulo bruto al objetivo, con ``phi_objetivo`` en grados.

    Con objetivo +30° (FP 0,87 inductivo) y un bruto dado, devuelve el valor de ``correccion_angular_fases``.
    """
    return normalizar_grados(phi_bruto - phi_objetivo)


def candidatos_angulo_bruto(
    magnitud_antes: float,
    alpha_antes: float,
    magnitud_despues: float,
    alpha_despues: float,
    tolerancia: float = 2.0,
) -> list[float]:
    """Ángulos brutos compatibles con dos mediciones de la misma fase bajo dos correcciones.

    Cada medición da φ_bruto = ±|φ| + alfa, así que hay cuatro combinaciones de signo. Se devuelven las
    que coinciden entre las dos mediciones, con una tolerancia en grados, normalizadas a (-180, 180].
    Con una sola combinación el ángulo está determinado; con dos, el signo de Q es indeterminado.
    """
    candidatos: list[float] = []
    for signo_antes in (1, -1):
        bruto_antes = normalizar_grados(signo_antes * magnitud_antes + alpha_antes)
        for signo_despues in (1, -1):
            bruto_despues = normalizar_grados(signo_despues * magnitud_despues + alpha_despues)
            if abs(normalizar_grados(bruto_antes - bruto_despues)) <= tolerancia:
                candidatos.append(round((bruto_antes + bruto_despues) / 2.0, 1))
    return sorted({normalizar_grados(c) for c in candidatos})
