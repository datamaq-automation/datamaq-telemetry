"""tests/unit/test_desagregador_asistido.py — Pruebas unitarias para desagregación asistida por sensores de proceso en TGBT."""

from datetime import datetime, timezone

import pytest

from src.domain.maquinas.servicios.desagregador_asistido import (
    DesagregadorAsistidoService,
)

INICIO = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)


def test_desagregacion_atribuye_potencia_cuando_sensor_inductivo_esta_activo():
    """Un salto en TGBT de 40 kW a 85 kW coincide con sensor inductivo activo en máquina de 45 kW."""
    p_tgbt = 85000.0
    p_base = 40000.0
    q_tgbt = 42000.0
    p_nominal_maquina = 45000.0  # Motor de 45 kW

    resultado = DesagregadorAsistidoService.desagregar_intervalo(
        potencia_tgbt_w=p_tgbt,
        potencia_base_w=p_base,
        potencia_reactiva_var=q_tgbt,
        sensor_inductivo_activo=True,
        potencia_nominal_w=p_nominal_maquina,
    )

    assert resultado.atribuido is True
    assert resultado.potencia_maquina_w == pytest.approx(45000.0)
    assert resultado.potencia_residual_w == pytest.approx(40000.0)
    assert resultado.confianza >= 0.90
    assert "Sensor inductivo activo" in resultado.motivo


def test_desagregacion_rechaza_atribucion_cuando_sensor_inductivo_esta_inactivo():
    """Si el sensor inductivo estuvo inactivo, el aumento de potencia no se atribuye a esa máquina."""
    p_tgbt = 85000.0
    p_base = 40000.0
    p_nominal_maquina = 45000.0

    resultado = DesagregadorAsistidoService.desagregar_intervalo(
        potencia_tgbt_w=p_tgbt,
        potencia_base_w=p_base,
        potencia_reactiva_var=None,
        sensor_inductivo_activo=False,
        potencia_nominal_w=p_nominal_maquina,
    )

    assert resultado.atribuido is False
    assert resultado.potencia_maquina_w == 0.0
    assert resultado.potencia_residual_w == pytest.approx(85000.0)
    assert "Sensor inactivo" in resultado.motivo
