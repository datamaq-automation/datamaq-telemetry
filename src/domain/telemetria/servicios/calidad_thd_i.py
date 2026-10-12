"""src/domain/telemetria/servicios/calidad_thd_i.py — Fiabilidad del THD_I por fase.

El THD_I del equipo se calcula contra la corriente fundamental instantánea: con corriente casi nula
da valores sin significado (992,5 % con 0,022 A en un backup). Solo es representativo si la corriente
de la fase supera un porcentaje de la corriente nominal real del TI declarada en el YAML.
"""

# Umbral interno y configurable. No es normativo: no hay norma que lo fundamente; lo aprobó el dueño
# (decisión del 2026-10-09, confirmado 2026-10-11).
UMBRAL_FIABILIDAD_THD_I_PCT_DE_NOMINAL: float = 10.0


def es_thd_i_fiable(corriente_a: float | None, corriente_nominal_ti_a: float | None) -> bool | None:
    """Devuelve True/False si hay corriente medida y TI declarado; None si no se puede determinar.

    Sin TI declarado nunca se devuelve True: el THD_I no tiene base para considerarse representativo.
    """
    if corriente_a is None or corriente_nominal_ti_a is None or corriente_nominal_ti_a <= 0.0:
        return None
    minimo_a = corriente_nominal_ti_a * UMBRAL_FIABILIDAD_THD_I_PCT_DE_NOMINAL / 100.0
    return corriente_a > minimo_a
