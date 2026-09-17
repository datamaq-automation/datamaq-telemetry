"""Tests para corrección fasorial por software e integración de energía."""

from datetime import datetime, timezone

from src.application.mappers.energia_parser import EnergiaPayloadParser
from src.application.mappers.fase_parser import rotar_fase_fasorial
from src.application.mappers.payload_telemetria_parser import TelemetriaPayloadParser
from src.domain.telemetria.entities import Dispositivo, MedicionFase
from src.domain.telemetria.value_objects import (
    FactorPotencia,
    MacAddress,
    PotenciaActiva,
    PotenciaAparente,
    PotenciaReactiva,
)


def test_rotar_fase_fasorial_matematica_fase_r():
    # Fase R: P = 22.25 kW, Q = -55.79 kvar (FP = 0.37, phi = -68.3°)
    fase_r = MedicionFase(
        potencia_activa=PotenciaActiva(vatios=22250.0),
        potencia_reactiva=PotenciaReactiva(var=-55790.0),
        potencia_aparente=PotenciaAparente(va=60060.0),
        factor_potencia=FactorPotencia(valor=0.37),
    )

    # Rotación de -60°
    fase_r_corr = rotar_fase_fasorial(fase_r, -60.0)

    # P' = 22250 * 0.5 + (-55790) * (-0.866025) = 11125 + 48315.5 = 59440.5 W (~59.44 kW)
    # Q' = (-55790) * 0.5 - 22250 * (-0.866025) = -27895 + 19269 = -8626 VAR (~-8.63 kvar)
    assert fase_r_corr.potencia_activa is not None
    assert abs(fase_r_corr.potencia_activa.vatios - 59440.5) < 50.0

    assert fase_r_corr.potencia_reactiva is not None
    assert abs(fase_r_corr.potencia_reactiva.var - (-8626.0)) < 50.0

    assert fase_r_corr.factor_potencia is not None
    assert abs(fase_r_corr.factor_potencia.valor - 0.99) < 0.02


def test_rotar_fase_fasorial_matematica_fase_s():
    # Fase S: P = 32.04 kW, Q = +55.18 kvar (FP = 0.50, phi = +59.9°)
    fase_s = MedicionFase(
        potencia_activa=PotenciaActiva(vatios=32040.0),
        potencia_reactiva=PotenciaReactiva(var=55180.0),
        potencia_aparente=PotenciaAparente(va=63810.0),
        factor_potencia=FactorPotencia(valor=0.50),
    )

    # Rotación de +60°
    fase_s_corr = rotar_fase_fasorial(fase_s, 60.0)

    # P' = 32040 * 0.5 + 55180 * (0.866025) = 16020 + 47787.2 = 63807.2 W (~63.81 kW)
    # Q' = 55180 * 0.5 - 32040 * (0.866025) = 27590 - 27749.4 = -159.4 VAR (~-0.16 kvar)
    assert fase_s_corr.potencia_activa is not None
    assert abs(fase_s_corr.potencia_activa.vatios - 63807.2) < 50.0

    assert fase_s_corr.factor_potencia is not None
    assert abs(fase_s_corr.factor_potencia.valor - 1.00) < 0.02


def test_rotar_fase_fasorial_matematica_fase_s_orden_fases_120():
    # Fase S con secuencia/orden de fases invertido: P = -67501 W, Q = 53500 VAR (FP = -0.75)
    fase_s = MedicionFase(
        potencia_activa=PotenciaActiva(vatios=-67501.0),
        potencia_reactiva=PotenciaReactiva(var=53500.0),
        potencia_aparente=PotenciaAparente(va=86133.4),
        factor_potencia=FactorPotencia(valor=-0.75),
    )

    # Rotación de +120° (resta 120° al ángulo del fasor, llevando de +141.6° a +21.6°)
    fase_s_corr = rotar_fase_fasorial(fase_s, 120.0)

    # P' = (-67501) * (-0.5) + 53500 * (0.866025) = 33750.5 + 46332.3 = 80082.8 W (~80.08 kW)
    assert fase_s_corr.potencia_activa is not None
    assert abs(fase_s_corr.potencia_activa.vatios - 80082.8) < 100.0
    assert fase_s_corr.potencia_activa.vatios > 0  # Potencia se vuelve activa y positiva

    assert fase_s_corr.factor_potencia is not None
    assert abs(fase_s_corr.factor_potencia.valor - 0.93) < 0.03


def test_parsear_instantanea_con_correccion_angular_dispositivo():
    dispositivo = Dispositivo(
        id="364",
        device_uid=MacAddress("D4:8C:49:F0:35:A8"),
        nombre="Planta San Martín - Trafo1",
        correccion_angular_fases="R:-60,S:60",
    )

    payload = {
        "fase_r": {"p": 22250.0, "q": -55790.0, "v": 220.0, "i": 273.0},
        "fase_s": {"p": 32040.0, "q": 55180.0, "v": 220.0, "i": 290.0},
        "fase_t": {"p": 0.0, "q": 0.0, "v": 220.0, "i": 0.0},
    }

    now = datetime.now(timezone.utc)
    lectura = TelemetriaPayloadParser.parsear_instantanea(payload, dispositivo, now)

    # Potencia activa total corregida debe ser ~123 kW en lugar de ~54 kW
    assert lectura.potencia_activa_total is not None
    assert abs(lectura.potencia_activa_total.vatios - 123247.7) < 500.0

    assert lectura.factor_potencia_total is not None
    assert lectura.factor_potencia_total.valor > 0.95


def test_parsear_acumulado_con_correccion_angular():
    payload = {
        "f": [
            {"n": "R", "a": 22.25, "r": -55.79},
            {"n": "S", "a": 32.04, "r": 55.18},
            {"n": "T", "a": 0.0, "r": 0.0},
        ]
    }

    now = datetime.now(timezone.utc)
    acumulado = EnergiaPayloadParser.parsear_acumulado(payload, "364", now, correccion_angular="R:-60,S:60")

    assert acumulado.energia_activa_neta is not None
    # La energía activa acumulada corregida debe ser ~123.25 kWh
    assert abs(acumulado.energia_activa_neta.kwh - 123.25) < 1.0
