"""tests/unit/test_calculador_ahorros_iso.py — Pruebas para cálculo de ahorros y CUSUM según ISO 50006."""

from datetime import datetime, timezone

import pytest

from src.domain.produccion.servicios.calculador_ahorros_iso import (
    CalculadorAhorrosIsoService,
    LineaBaseCongelada,
)

INICIO_REF = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
FIN_REF = datetime(2026, 3, 31, 23, 59, tzinfo=timezone.utc)


def test_evaluar_periodo_con_ahorro_positivo_demuestra_mejora():
    """Si la máquina produce 5000 metros y gasta menos que la EnB, registra ahorro positivo."""
    enb = LineaBaseCongelada(
        id="enb-planta-corte",
        nombre="Línea de Base 1T 2026",
        sec_referencia=0.05,  # 0.05 kWh/metro
        potencia_base_kw=10.0,  # 10 kW fijos
        periodo_referencia_desde=INICIO_REF,
        periodo_referencia_hasta=FIN_REF,
        congelada_en=FIN_REF,
    )

    # 10 horas de turno, 5000 metros producidos
    # E_esperada = (10 kW * 10 h) + (0.05 kWh/m * 5000 m) = 100 + 250 = 350 kWh
    # E_real = 310 kWh -> Ahorro = 40 kWh (11.4% de mejora)
    res = CalculadorAhorrosIsoService.evaluar_periodo(
        linea_base=enb,
        unidades_producidas=5000.0,
        horas_periodo=10.0,
        energia_real_kwh=310.0,
    )

    assert res.es_mejora is True
    assert res.energia_esperada_kwh == pytest.approx(350.0)
    assert res.energia_real_kwh == pytest.approx(310.0)
    assert res.ahorro_kwh == pytest.approx(40.0)
    assert res.ahorro_porcentual == pytest.approx(0.1143, rel=1e-3)


def test_evaluar_periodo_con_sobreconsumo_detecta_degradacion():
    """Si la energía real supera la esperada, el ahorro es negativo."""
    enb = LineaBaseCongelada(
        id="enb-planta-corte",
        nombre="Línea de Base 1T 2026",
        sec_referencia=0.05,
        potencia_base_kw=10.0,
        periodo_referencia_desde=INICIO_REF,
        periodo_referencia_hasta=FIN_REF,
        congelada_en=FIN_REF,
    )

    res = CalculadorAhorrosIsoService.evaluar_periodo(
        linea_base=enb,
        unidades_producidas=5000.0,
        horas_periodo=10.0,
        energia_real_kwh=385.0,  # 35 kWh de sobreconsumo
    )

    assert res.es_mejora is False
    assert res.ahorro_kwh == pytest.approx(-35.0)
    assert res.ahorro_porcentual == pytest.approx(-0.10, rel=1e-2)


def test_acumulacion_cusum_de_ahorros():
    """El CUSUM integra la suma acumulada de ahorros en el tiempo."""
    ahorros = [10.0, 15.0, -5.0, 20.0, 10.0]
    cusum = CalculadorAhorrosIsoService.calcular_cusum(ahorros)

    assert cusum == [10.0, 25.0, 20.0, 40.0, 50.0]
