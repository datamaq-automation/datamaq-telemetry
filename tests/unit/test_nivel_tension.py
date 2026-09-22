"""tests/unit/test_nivel_tension.py — clasificación IEC 60038 y derivación de nominal fase-neutro."""

from src.domain.telemetria.servicios.clasificador_nivel_tension import (
    cantidad_de_fases,
    clasificar_nivel_tension,
    tension_nominal_de_fase_v,
)


def test_clasificar_nivel_tension_umbral_iec_60038() -> None:
    assert clasificar_nivel_tension(220.0) == "BT"
    assert clasificar_nivel_tension(380.0) == "BT"
    assert clasificar_nivel_tension(1000.0) == "BT"
    assert clasificar_nivel_tension(1000.1) == "MT"
    assert clasificar_nivel_tension(13200.0) == "MT"


def test_cantidad_de_fases_cuenta_las_declaradas() -> None:
    assert cantidad_de_fases("R") == 1
    assert cantidad_de_fases("R,S") == 2
    assert cantidad_de_fases("R,S,T") == 3


def test_cantidad_de_fases_sin_dato_asume_trifasico() -> None:
    assert cantidad_de_fases(None) == 3
    assert cantidad_de_fases("") == 3


def test_tension_nominal_de_fase_v_monofasico_nominal_ya_es_fase_neutro() -> None:
    assert tension_nominal_de_fase_v(220.0, fases=1) == 220.0


def test_tension_nominal_de_fase_v_polifasico_divide_por_raiz_de_3() -> None:
    assert round(tension_nominal_de_fase_v(380.0, fases=3), 1) == 219.4
    assert round(tension_nominal_de_fase_v(380.0, fases=2), 1) == 219.4
    assert round(tension_nominal_de_fase_v(13200.0, fases=3), 0) == 7621.0


def test_tension_nominal_de_fase_v_sin_fases_usa_heuristica_de_umbral() -> None:
    assert tension_nominal_de_fase_v(220.0) == 220.0
    assert round(tension_nominal_de_fase_v(380.0), 1) == 219.4
