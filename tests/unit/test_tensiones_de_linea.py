"""tests/unit/test_tensiones_de_linea.py — Tensiones compuestas y magnitud canónica por nivel."""

import pytest

from src.domain.telemetria.servicios.tensiones_de_linea import (
    magnitud_tension_canonica,
    tensiones_de_linea,
)

RAIZ_3 = 3**0.5


# --- magnitud_tension_canonica ---


def test_en_bt_la_magnitud_canonica_es_la_de_fase():
    """Estrella con neutro distribuido: la fase-neutro se mide en bornes."""
    assert magnitud_tension_canonica("BT") == "FASE"


def test_en_mt_la_magnitud_canonica_es_la_de_linea():
    """Red de 3 conductores con primario en triángulo (Dyn11): no hay neutro
    accesible, así que la fase-neutro es una referencia a un neutro virtual."""
    assert magnitud_tension_canonica("MT") == "LINEA"


# --- tensiones_de_linea ---


def test_sistema_equilibrado_da_la_identidad_raiz_de_tres():
    v_rs, v_st, v_tr = tensiones_de_linea(220.0, 220.0, 220.0)

    assert v_rs == pytest.approx(220.0 * RAIZ_3, abs=0.05)
    assert v_st == v_rs
    assert v_tr == v_rs


def test_barra_de_380_v_se_reconstruye_desde_sus_fases():
    """380 V entre fases ⇒ 219.4 V por fase; el camino de vuelta cierra."""
    v_rs, _, _ = tensiones_de_linea(219.4, 219.4, 219.4)

    assert v_rs == pytest.approx(380.0, abs=0.1)


def test_acometida_de_13200_v_se_reconstruye_desde_sus_fases():
    """El caso que motivó el cambio: 7621 V de fase son 13.2 kV entre fases."""
    v_rs, _, _ = tensiones_de_linea(7621.0, 7621.0, 7621.0)

    assert v_rs == pytest.approx(13200.0, abs=1.0)


def test_desequilibrio_se_conserva_entre_pares():
    """Con fases distintas, cada compuesta difiere: es la ventaja sobre aplicar
    √3 a un único promedio, que aplanaría el desequilibrio."""
    v_rs, v_st, v_tr = tensiones_de_linea(210.0, 220.0, 230.0)

    assert v_rs is not None and v_st is not None and v_tr is not None
    assert len({v_rs, v_st, v_tr}) == 3
    # El par con las dos fases más altas da la compuesta mayor.
    assert v_st > v_rs
    assert v_tr > v_rs


def test_el_orden_es_el_ciclico_de_secuencia_directa():
    """RS → ST → TR: cada compuesta se nombra por su par en el sentido de la
    secuencia. Verificado dejando una sola fase en cero."""
    v_rs, v_st, v_tr = tensiones_de_linea(100.0, 100.0, 0.0)

    assert v_rs == pytest.approx(100.0 * RAIZ_3, abs=0.05)  # R y S presentes
    assert v_st == pytest.approx(100.0)  # sólo S
    assert v_tr == pytest.approx(100.0)  # sólo R


@pytest.mark.parametrize(
    ("v_r", "v_s", "v_t", "esperado"),
    [
        (None, 220.0, 220.0, (None, True, None)),
        (220.0, None, 220.0, (None, None, True)),
        (None, None, None, (None, None, None)),
    ],
)
def test_un_par_incompleto_queda_en_none(v_r, v_s, v_t, esperado):
    """None, no cero: una fase sin dato no es una fase a 0 V."""
    resultado = tensiones_de_linea(v_r, v_s, v_t)

    for obtenido, esp in zip(resultado, esperado, strict=True):
        assert (obtenido is not None) == bool(esp)
