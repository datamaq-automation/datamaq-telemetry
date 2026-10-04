"""tests/unit/test_modelo_motor_industrial.py — Pruebas unitarias para el modelo físico de motores industriales."""

import pytest

from src.domain.maquinas.servicios.modelo_motor_industrial import (
    ModeloMotorFisicoService,
    RegimenMotorIndustrial,
)
from src.domain.maquinas.value_objects import OrigenFirma


def test_motor_en_vacio_detecta_baja_activa_y_alta_reactiva():
    """Un motor de 45 kW en vacío toma ~2 kW activos pero ~12 kVAr reactivos con cos phi bajo."""
    p_nom = 45000.0  # 45 kW
    p_medida = 2200.0  # ~5% de P_nom
    q_medida = 12500.0  # reactiva inductiva de magnetización

    diag = ModeloMotorFisicoService.estimar_regimen(
        potencia_w=p_medida,
        potencia_nominal_w=p_nom,
        potencia_reactiva_var=q_medida,
    )

    assert diag.es_compatible is True
    assert diag.regimen == RegimenMotorIndustrial.VACIO
    assert diag.factor_carga == pytest.approx(0.0488, rel=1e-2)
    assert diag.cos_phi is not None
    assert diag.cos_phi < 0.35  # Típico cos phi de vacío


def test_motor_a_carga_parcial_valida_factor_de_carga_y_cos_phi():
    """Un motor de 30 kW operando a 18 kW (60% de maquina) tiene cos phi ~0.78."""
    p_nom = 30000.0
    p_medida = 18000.0  # 60%
    q_medida = 14000.0

    diag = ModeloMotorFisicoService.estimar_regimen(
        potencia_w=p_medida,
        potencia_nominal_w=p_nom,
        potencia_reactiva_var=q_medida,
    )

    assert diag.es_compatible is True
    assert diag.regimen == RegimenMotorIndustrial.CARGA_PARCIAL
    assert diag.factor_carga == pytest.approx(0.60, rel=1e-2)
    assert diag.cos_phi is not None
    assert 0.70 <= diag.cos_phi <= 0.85


def test_motor_a_plena_carga_o_nominal():
    """Un motor de 15 kW operando a 14.5 kW está en régimen de plena maquina con alto factor de potencia."""
    p_nom = 15000.0
    p_medida = 14500.0
    q_medida = 8000.0

    diag = ModeloMotorFisicoService.estimar_regimen(
        potencia_w=p_medida,
        potencia_nominal_w=p_nom,
        potencia_reactiva_var=q_medida,
    )

    assert diag.es_compatible is True
    assert diag.regimen == RegimenMotorIndustrial.PLENA_CARGA
    assert diag.factor_carga == pytest.approx(0.966, rel=1e-2)
    assert diag.cos_phi is not None
    assert diag.cos_phi > 0.80


def test_sobrecarga_motor_supera_115_por_ciento():
    """Una potencia medida de 22 kW en motor de 15 kW indica sobrecarga."""
    p_nom = 15000.0
    p_medida = 22000.0
    q_medida = 15000.0

    diag = ModeloMotorFisicoService.estimar_regimen(
        potencia_w=p_medida,
        potencia_nominal_w=p_nom,
        potencia_reactiva_var=q_medida,
    )

    assert diag.regimen == RegimenMotorIndustrial.SOBRECARGA
    assert diag.factor_carga > 1.15


def test_potencia_desproporcionada_o_incompatible():
    """Un motor de 75 kW no puede explicar un consumo de 100 W resistivos."""
    p_nom = 75000.0
    p_medida = 100.0
    q_medida = 10.0

    diag = ModeloMotorFisicoService.estimar_regimen(
        potencia_w=p_medida,
        potencia_nominal_w=p_nom,
        potencia_reactiva_var=q_medida,
    )

    assert diag.es_compatible is False
    assert diag.regimen == RegimenMotorIndustrial.NO_COINCIDE


def test_generar_firma_desde_chapa_produce_valores_fisicos_coherentes():
    """Generar firma a partir de potencia declarada de 22 kW calcula reactiva y cos phi esperados."""
    p_nom = 22000.0
    firma = ModeloMotorFisicoService.generar_firma_desde_chapa(
        potencia_nominal_w=p_nom,
        factor_carga_esperado=0.75,
    )

    assert firma.potencia_w == pytest.approx(16500.0)  # 75% de 22 kW
    assert firma.potencia_reactiva_var is not None
    assert firma.potencia_reactiva_var > 0.0
    assert firma.factor_potencia is not None
    assert 0.75 <= firma.factor_potencia <= 0.88
    assert firma.origen == OrigenFirma.CHAPA
