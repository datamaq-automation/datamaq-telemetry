"""tests/unit/test_balance_energia_sge.py — Pruebas para balance de energía en TGBT según ISO 50001 §6.3."""

import pytest

from src.domain.sge.servicios.balance_energia import (
    BalanceEnergiaService,
    EstadoBalanceEnergia,
)


def test_balance_energia_normal_con_perdidas_tecnicas():
    """Un TGBT con 1000 kWh y 970 kWh en seccionales tiene un residual de 3% (admisible por pérdidas)."""
    e_padre = 1000.0
    e_hijos = [500.0, 320.0, 150.0]  # Suma = 970 kWh

    bal = BalanceEnergiaService.evaluar_balance(
        energia_padre_kwh=e_padre,
        energias_hijos_kwh=e_hijos,
    )

    assert bal.estado == EstadoBalanceEnergia.CONCILIADO_NORMAL
    assert bal.es_auditable_iso50001 is True
    assert bal.residual_kwh == pytest.approx(30.0)
    assert bal.residual_porcentual == pytest.approx(0.03)


def test_balance_energia_con_desbalance_critico_alerta_fuga():
    """Si el residual supera el 10%, se denuncia desbalance crítico (maquina no medida o fuga)."""
    e_padre = 1000.0
    e_hijos = [400.0, 300.0, 150.0]  # Suma = 850 kWh -> 15% residual

    bal = BalanceEnergiaService.evaluar_balance(
        energia_padre_kwh=e_padre,
        energias_hijos_kwh=e_hijos,
    )

    assert bal.estado == EstadoBalanceEnergia.DESBALANCE_CRITICO
    assert bal.es_auditable_iso50001 is False
    assert bal.residual_kwh == pytest.approx(150.0)


def test_balance_energia_con_sobreconteo_detecta_error_metrologico():
    """Si los hijos suman más que el padre, hay sobreconteo o error de relación de TI."""
    e_padre = 1000.0
    e_hijos = [600.0, 500.0]  # Suma = 1100 kWh

    bal = BalanceEnergiaService.evaluar_balance(
        energia_padre_kwh=e_padre,
        energias_hijos_kwh=e_hijos,
    )

    assert bal.estado == EstadoBalanceEnergia.SOBRECONTEO
    assert bal.es_auditable_iso50001 is False
    assert bal.residual_kwh == pytest.approx(-100.0)


def test_balance_energia_con_armonicos_elevados_explica_perdidas():
    """Un residual del 6% con THD_I del 22% se cataloga como pérdidas por armónicos (IEEE 519)."""
    e_padre = 1000.0
    e_hijos = [500.0, 440.0]  # Suma = 940 kWh -> 6% residual
    thd_i = 22.5  # % > 15% IEEE 519

    bal = BalanceEnergiaService.evaluar_balance(
        energia_padre_kwh=e_padre,
        energias_hijos_kwh=e_hijos,
        thd_i_promedio_pct=thd_i,
    )

    assert bal.estado == EstadoBalanceEnergia.PERDIDAS_ELEVADAS_POR_ARMONICOS
    assert bal.es_auditable_iso50001 is True
    assert "distorsión armónica" in bal.detalle
    assert bal.thd_i_promedio_pct == pytest.approx(22.5)
