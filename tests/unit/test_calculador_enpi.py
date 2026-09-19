"""tests/unit/test_calculador_enpi.py — Pruebas unitarias para cálculo de EnPI y Consumo Específico de Energía (ISO 50001/50006)."""

from datetime import datetime, timezone

import pytest

from src.domain.produccion.servicios.calculador_enpi import CalculadorEnPIService
from src.domain.produccion.value_objects import LecturaVariableProceso, TipoVariableProceso

INICIO = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)
FIN = datetime(2026, 9, 1, 16, 0, tzinfo=timezone.utc)


def test_calculo_sec_consumo_especifico_por_metro():
    """Calcula kWh/metro para avance de materia prima."""
    energia_kwh = 120.5
    metros = 2500.0

    sec = CalculadorEnPIService.calcular_sec(energia_kwh=energia_kwh, delta_unidades=metros)

    assert sec == pytest.approx(0.0482, rel=1e-3)


def test_calculo_sec_consumo_especifico_por_corte():
    """Calcula kWh/corte para impactos de corte con sensor inductivo."""
    energia_kwh = 35.0
    cortes = 1400.0

    sec = CalculadorEnPIService.calcular_sec(energia_kwh=energia_kwh, delta_unidades=cortes)

    assert sec == pytest.approx(0.025, rel=1e-3)


def test_sec_con_unidades_cero_retorna_none():
    """Si no hubo producción, el SEC no se calcula para evitar división por cero."""
    assert CalculadorEnPIService.calcular_sec(energia_kwh=10.0, delta_unidades=0.0) is None
    assert CalculadorEnPIService.calcular_sec(energia_kwh=10.0, delta_unidades=-5.0) is None


def test_generar_metricas_enpi_completas():
    """Genera objeto de métricas EnPI a partir de serie de lecturas de proceso."""
    lecturas = [
        LecturaVariableProceso(
            momento=INICIO,
            variable_tipo=TipoVariableProceso.LONGITUD_METROS,
            delta_valor=1000.0,
            valor_acumulado=1000.0,
        ),
        LecturaVariableProceso(
            momento=FIN,
            variable_tipo=TipoVariableProceso.LONGITUD_METROS,
            delta_valor=1500.0,
            valor_acumulado=2500.0,
        ),
    ]

    metricas = CalculadorEnPIService.calcular_metricas(
        periodo_inicio=INICIO,
        periodo_fin=FIN,
        energia_kwh=125.0,
        lecturas_proceso=lecturas,
        tipo=TipoVariableProceso.LONGITUD_METROS,
    )

    assert metricas.energia_kwh == 125.0
    assert metricas.unidades_procesadas == 2500.0
    assert metricas.sec_kwh_por_unidad == pytest.approx(0.05)


def test_discriminar_consumo_basal_vs_proceso():
    """Separa la energía de planta entre consumo inelástico de base y consumo de producción."""
    energia_total = 200.0
    horas_totales = 8.0
    horas_produciendo = 6.0
    potencia_base_kw = 10.0  # 10 kW fijos en vacío

    e_base, e_proceso = CalculadorEnPIService.discriminar_consumo_basal(
        energia_total_kwh=energia_total,
        horas_periodo=horas_totales,
        horas_en_produccion=horas_produciendo,
        potencia_base_kw=potencia_base_kw,
    )

    assert e_base == pytest.approx(80.0)  # 10 kW * 8 h
    assert e_proceso == pytest.approx(120.0)  # 200 - 80
