"""tests/unit/test_presets_industriales.py — Pruebas para el catálogo de maquinaria industrial."""

import pytest

from src.domain.maquinas.servicios.presets_industriales import CatalogoPresetsIndustriales
from src.domain.maquinas.value_objects import CategoriaCarga, NaturalezaElectrica, OrigenFirma


def test_catalogo_crea_motor_11kw_con_parametros_industriales():
    maquina = CatalogoPresetsIndustriales.crear_motor_trifasico_11kw(
        dispositivo_id="dev-1",
        carga_id="motor-principal",
    )

    assert maquina.potencia_nominal_w == 11000.0
    assert maquina.categoria == CategoriaCarga.FUERZA_MOTRIZ
    assert maquina.naturaleza_electrica == NaturalezaElectrica.MOTOR
    assert maquina.firma is not None
    assert maquina.firma.origen == OrigenFirma.CHAPA
    # 75% maquina esperada = 8250 W
    assert maquina.firma.potencia_w == pytest.approx(8250.0)
    assert maquina.firma.potencia_reactiva_var is not None
    assert maquina.firma.potencia_reactiva_var > 0.0


def test_catalogo_crea_horno_resistivo_industrial():
    maquina = CatalogoPresetsIndustriales.crear_horno_resistivo_50kw(
        dispositivo_id="dev-1",
        carga_id="horno-tratamiento",
    )

    assert maquina.potencia_nominal_w == 50000.0
    assert maquina.categoria == CategoriaCarga.OTROS
    assert maquina.naturaleza_electrica == NaturalezaElectrica.RESISTIVA
    assert maquina.firma is not None
    assert maquina.firma.potencia_w == 50000.0
    assert maquina.firma.factor_potencia == pytest.approx(1.0)
    assert maquina.firma.potencia_reactiva_var == pytest.approx(0.0)
