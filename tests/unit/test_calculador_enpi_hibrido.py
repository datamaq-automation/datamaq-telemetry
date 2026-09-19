"""tests/unit/test_calculador_enpi_hibrido.py — Tests para cálculo de SEC híbrido (ISO 50001 / ISO 50006)."""

from datetime import datetime, timezone

import pytest

from src.domain.produccion.entities import (
    ConfiguracionMedicionMaquina,
    ModoMedicion,
    ResultadoSecHibrido,
)
from src.domain.produccion.servicios.calculador_enpi_hibrido import CalculadorEnpiHibridoService


@pytest.fixture
def config_maquina_dedicada() -> ConfiguracionMedicionMaquina:
    return ConfiguracionMedicionMaquina(
        maquina_id="cortadora-01",
        nombre="Cortadora Automática Chapa L1",
        potencia_nominal_kw=15.0,
        nodo_alimentacion="CCM-LINEA-1",
        dispositivo_medidor_id="esp32-ccm-cortadora",
        factor_escala_longitud=1.0,
        factor_escala_cortes=1.0,
    )


@pytest.fixture
def config_maquina_tgbt() -> ConfiguracionMedicionMaquina:
    return ConfiguracionMedicionMaquina(
        maquina_id="conformadora-02",
        nombre="Conformadora de Perfiles",
        potencia_nominal_kw=30.0,
        nodo_alimentacion="TGBT-PRINCIPAL",
        dispositivo_medidor_id=None,
        factor_escala_longitud=0.5,
        factor_escala_cortes=1.0,
    )


def test_configuracion_detecta_modo_medicion_correctamente(config_maquina_dedicada, config_maquina_tgbt):
    assert config_maquina_dedicada.es_medicion_dedicada is True
    assert config_maquina_dedicada.modo_medicion == ModoMedicion.DEDICADA_SECCIONAL

    assert config_maquina_tgbt.es_medicion_dedicada is False
    assert config_maquina_tgbt.modo_medicion == ModoMedicion.AGREGADA_TGBT


def test_calculo_sec_modo_dedicado_puro(config_maquina_dedicada):
    t0 = datetime(2026, 9, 19, 8, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)

    # 4 horas, 40 kWh consumidos en el medidor dedicado, 200 metros cortados
    # 30 kWh consumidos mientras producía, 10 kWh en vacío
    resultado: ResultadoSecHibrido = CalculadorEnpiHibridoService.calcular(
        config=config_maquina_dedicada,
        periodo_inicio=t0,
        periodo_fin=t1,
        energia_kwh=40.0,
        unidades_produccion=200.0,
        horas_activas_proceso=3.0,
        potencia_media_kw=10.0,
    )

    assert resultado.modo_medicion == ModoMedicion.DEDICADA_SECCIONAL
    assert resultado.sec_kwh_por_unidad == 0.2  # 40 kWh / 200 m = 0.2 kWh/m
    assert resultado.energia_total_kwh == 40.0
    # 3 horas activas * 10 kW = 30 kWh productiva
    assert resultado.energia_productiva_kwh == 30.0
    # 1 hora en vacío = 10 kWh desperdicio
    assert resultado.energia_no_productiva_kwh == 10.0
    assert resultado.ratio_desperdicio_pct == 25.0


def test_calculo_sec_modo_tgbt_desagregado(config_maquina_tgbt):
    t0 = datetime(2026, 9, 19, 8, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 9, 19, 16, 0, tzinfo=timezone.utc)

    # 8 horas, 500 kWh consumidos en el TGBT general (toda la planta)
    # Máquina de 30 kW operando a LF 0.7 (21 kW) durante 5 horas activas registradas por sensor
    # Producción = 1000 metros
    resultado: ResultadoSecHibrido = CalculadorEnpiHibridoService.calcular(
        config=config_maquina_tgbt,
        periodo_inicio=t0,
        periodo_fin=t1,
        energia_kwh=500.0,
        unidades_produccion=1000.0,
        horas_activas_proceso=5.0,
        factor_carga_estimado=0.7,
    )

    assert resultado.modo_medicion == ModoMedicion.AGREGADA_TGBT
    # Energía estimada máquina = 30 kW * 0.7 * 5 h = 105 kWh
    assert resultado.energia_productiva_kwh == 105.0
    # SEC estimado de máquina = 105 kWh / 1000 m = 0.105 kWh/m
    assert resultado.sec_kwh_por_unidad == 0.105
    # Energía no atribuible a la máquina (resto de planta) = 500 - 105 = 395 kWh
    assert resultado.energia_no_productiva_kwh == 395.0
    assert resultado.ratio_desperdicio_pct == 79.0
    assert "Desagregación asistida en TGBT" in (resultado.detalle_estimacion or "")


def test_calculo_sec_sin_produccion_retorna_sec_none(config_maquina_dedicada):
    t0 = datetime(2026, 9, 19, 8, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 9, 19, 9, 0, tzinfo=timezone.utc)

    resultado = CalculadorEnpiHibridoService.calcular(
        config=config_maquina_dedicada,
        periodo_inicio=t0,
        periodo_fin=t1,
        energia_kwh=5.0,
        unidades_produccion=0.0,
        horas_activas_proceso=0.0,
        potencia_media_kw=5.0,
    )
    assert resultado.sec_kwh_por_unidad is None
    assert resultado.energia_productiva_kwh == 0.0
    assert resultado.energia_no_productiva_kwh == 5.0
    assert resultado.ratio_desperdicio_pct == 100.0
