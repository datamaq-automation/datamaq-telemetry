"""tests/unit/test_calidad_thd_i.py — Fiabilidad del THD_I según la corriente nominal del TI (decisión 2026-10-09)."""

import pytest

from src.domain.telemetria.servicios.calidad_thd_i import (
    UMBRAL_FIABILIDAD_THD_I_PCT_DE_NOMINAL,
    es_thd_i_fiable,
)


def test_umbral_provisional_es_10_por_ciento():
    assert UMBRAL_FIABILIDAD_THD_I_PCT_DE_NOMINAL == 10.0


def test_sin_ti_declarado_devuelve_none_nunca_true():
    assert es_thd_i_fiable(corriente_a=50.0, corriente_nominal_ti_a=None) is None


def test_sin_corriente_medida_devuelve_none():
    assert es_thd_i_fiable(corriente_a=None, corriente_nominal_ti_a=100.0) is None


def test_nominal_no_positiva_devuelve_none():
    assert es_thd_i_fiable(corriente_a=5.0, corriente_nominal_ti_a=0.0) is None
    assert es_thd_i_fiable(corriente_a=5.0, corriente_nominal_ti_a=-100.0) is None


@pytest.mark.parametrize(
    ("corriente_a", "esperado"),
    [
        (0.022, False),  # caso real del backup: fundamental casi nula
        (10.0, False),  # exactamente el 10 %: no supera el umbral
        (10.01, True),
        (60.0, True),
    ],
)
def test_fiable_si_supera_el_porcentaje_de_la_nominal(corriente_a: float, esperado: bool):
    assert es_thd_i_fiable(corriente_a=corriente_a, corriente_nominal_ti_a=100.0) is esperado
