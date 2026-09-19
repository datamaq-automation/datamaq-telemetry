"""tests/unit/test_presets_industriales.py — Pruebas para el catálogo de maquinaria industrial."""

import pytest

from src.domain.cargas.servicios.presets_industriales import CatalogoPresetsIndustriales
from src.domain.cargas.value_objects import CategoriaCarga, NaturalezaElectrica, OrigenFirma


def test_catalogo_crea_motor_11kw_con_parametros_industriales():
    carga = CatalogoPresetsIndustriales.crear_motor_trifasico_11kw(
        dispositivo_id="dev-1",
        carga_id="motor-principal",
    )

    assert carga.potencia_nominal_w == 11000.0
    assert carga.categoria == CategoriaCarga.FUERZA_MOTRIZ
    assert carga.naturaleza_electrica == NaturalezaElectrica.MOTOR
    assert carga.firma is not None
    assert carga.firma.origen == OrigenFirma.CHAPA
    # 75% carga esperada = 8250 W
    assert carga.firma.potencia_w == pytest.approx(8250.0)
    assert carga.firma.potencia_reactiva_var is not None
    assert carga.firma.potencia_reactiva_var > 0.0


def test_catalogo_crea_horno_resistivo_industrial():
    carga = CatalogoPresetsIndustriales.crear_horno_resistivo_50kw(
        dispositivo_id="dev-1",
        carga_id="horno-tratamiento",
    )

    assert carga.potencia_nominal_w == 50000.0
    assert carga.categoria == CategoriaCarga.OTROS
    assert carga.naturaleza_electrica == NaturalezaElectrica.RESISTIVA
    assert carga.firma is not None
    assert carga.firma.potencia_w == 50000.0
    assert carga.firma.factor_potencia == pytest.approx(1.0)
    assert carga.firma.potencia_reactiva_var == pytest.approx(0.0)
