"""src/domain/telemetria/servicios/clasificador_nivel_tension.py."""

from typing import Literal

NivelTension = Literal["MT", "BT"]

# Umbral de clasificación MT/BT (IEC 60038): >1000 V AC es Media Tensión.
UMBRAL_MEDIA_TENSION_V = 1000.0

# El YAML no declara cantidad de fases por nodo. Convención de lectura: una
# instalación monofásica argentina es 220 V (fase-neutro); toda nominal por
# encima de este techo se interpreta como tensión entre fases (V_LL).
TENSION_MAXIMA_MONOFASICA_V = 250.0


def clasificar_nivel_tension(tension_nominal_v: float) -> NivelTension:
    """Clasifica una tensión nominal en Media o Baja Tensión (IEC 60038)."""
    return "MT" if tension_nominal_v > UMBRAL_MEDIA_TENSION_V else "BT"


def cantidad_de_fases(fases_con_ti: str | None) -> int:
    """Cuenta las fases declaradas en un ``fases_con_ti`` tipo "R,S,T".

    Devuelve 3 si no hay dato (mismo default que ``Dispositivo.fases_con_ti``).
    """
    if not fases_con_ti:
        return 3
    return len([f for f in fases_con_ti.split(",") if f.strip()])


def tension_nominal_de_fase_v(tension_nominal_v: float, fases: int | None = None) -> float:
    """Deriva la tensión nominal fase-neutro (V_LN) de la nominal declarada.

    Si se conoce la cantidad de fases: 1 fase → la nominal ya es V_LN (ej. una
    acometida monofásica de 220 V); más de 1 fase → se asume nominal entre
    fases (V_LL) y se divide por √3. Sin ese dato (nodo virtual, sin
    dispositivo asociado) se aplica ``TENSION_MAXIMA_MONOFASICA_V`` como
    frontera de la misma regla.
    """
    if fases == 1:
        return tension_nominal_v
    if fases is not None and fases > 1:
        return tension_nominal_v / 3**0.5
    if tension_nominal_v <= TENSION_MAXIMA_MONOFASICA_V:
        return tension_nominal_v
    return tension_nominal_v / 3**0.5
