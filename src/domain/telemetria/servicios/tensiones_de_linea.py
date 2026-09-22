"""src/domain/telemetria/servicios/tensiones_de_linea.py."""

from typing import Literal

# Qué magnitud de tensión es la físicamente accesible en un nodo.
MagnitudTension = Literal["LINEA", "FASE"]


def magnitud_tension_canonica(nivel_tension: str) -> MagnitudTension:
    """Qué tensión tiene sentido mostrar para un nodo, según su nivel.

    En BT la distribución es estrella con neutro distribuido (400/230 V, 380/220 V
    en la práctica argentina): la tensión fase-neutro es una magnitud medible en
    cada fase, y es la que reportan los medidores.

    En MT la red de distribución es trifásica de tres conductores y el primario de
    los transformadores va en triángulo (los de Durax declaran ``Dyn11``: D =
    triángulo del lado de mayor tensión, yn = estrella con neutro del lado de
    menor tensión). Sin neutro accesible, la tensión fase-neutro es una referencia
    a un neutro virtual, no algo que exista en bornes: lo real son las tensiones
    compuestas V_RS, V_ST y V_TR. Por eso un nodo de 13.2 kV se lee en 13.2 kV
    entre fases, no en los 7.62 kV de su fase-neutro calculada.
    """
    return "LINEA" if nivel_tension == "MT" else "FASE"


def _compuesta(v_a: float | None, v_b: float | None) -> float | None:
    """|V_a - V_b| para dos fases separadas 120°.

    Del teorema del coseno sobre la resta de fasores:
    |V_a - V_b|² = V_a² + V_b² - 2·V_a·V_b·cos(120°) = V_a² + V_b² + V_a·V_b.

    Con las tres fases equilibradas se reduce a la identidad conocida V_LL = V_LN·√3,
    pero ante desequilibrio conserva la diferencia entre pares en vez de aplanarla
    a un único promedio. **Asume 120° exactos**: el agregado no lleva los ángulos
    de fase medidos, así que un desequilibrio angular real no queda reflejado.
    """
    if v_a is None or v_b is None:
        return None
    return round((v_a**2 + v_b**2 + v_a * v_b) ** 0.5, 1)


def tensiones_de_linea(
    v_r: float | None, v_s: float | None, v_t: float | None
) -> tuple[float | None, float | None, float | None]:
    """Deriva (V_RS, V_ST, V_TR) de las tensiones fase-neutro de R, S y T.

    El orden RS → ST → TR es el cíclico de secuencia directa (IEC 60038 / IEEE
    1159): cada compuesta se nombra por el par en el sentido de la secuencia.
    Un par vacío queda en ``None`` en vez de propagar un cero engañoso.
    """
    return _compuesta(v_r, v_s), _compuesta(v_s, v_t), _compuesta(v_t, v_r)
