# tests/unit/test_supresion_alertas_fp_ti.py
"""Tests unitarios para verificar la supresión de falsas alertas de FP cuando hay anomalía de TIs."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from src.application.use_cases.ingesta.procesador_alertas_ingesta import (
    ProcesadorAlertasIngesta,
)
from src.domain.telemetria.entities import Dispositivo, LecturaInstantanea, MedicionFase
from src.domain.telemetria.value_objects import (
    Corriente,
    FactorPotencia,
    MacAddress,
    PotenciaActiva,
    PotenciaAparente,
    PotenciaReactiva,
    Tension,
)


def _crear_dispositivo_constituyentes() -> Dispositivo:
    return Dispositivo(
        id="D48C49F035A8",
        device_uid=MacAddress("D4:8C:49:F0:35:A8"),
        nombre="Medidor General Los Constituyentes",
        modelo="Powermeter Trifásico",
        planta_id="6a182b0f-6406-4bc2-adf3-a4d2754198af",
        tipo_instalacion="CONSUMO",
        fases_con_ti="R,S,T",
    )


def _crear_lectura_con_ti_duplicado() -> LecturaInstantanea:
    fase_r = MedicionFase(
        tension=Tension(219.0),
        corriente=Corriente(287.0),
        potencia_activa=PotenciaActiva(2500.0),
        potencia_reactiva=PotenciaReactiva(-62800.0),
        potencia_aparente=PotenciaAparente(62850.0),
        factor_potencia=FactorPotencia(0.04),
    )
    fase_s = MedicionFase(
        tension=Tension(219.0),
        corriente=Corriente(287.0),
        potencia_activa=PotenciaActiva(59000.0),
        potencia_reactiva=PotenciaReactiva(20000.0),
        potencia_aparente=PotenciaAparente(62300.0),
        factor_potencia=FactorPotencia(0.94),
    )
    fase_t = MedicionFase(
        tension=Tension(220.0),
        corriente=Corriente(0.0),
        potencia_activa=PotenciaActiva(0.0),
        potencia_reactiva=PotenciaReactiva(0.0),
        potencia_aparente=PotenciaAparente(0.0),
        factor_potencia=FactorPotencia(0.0),
    )
    return LecturaInstantanea(
        id=10,
        dispositivo_id="D48C49F035A8",
        registrado_en=datetime.now(timezone.utc),
        fase_r=fase_r,
        fase_s=fase_s,
        fase_t=fase_t,
        potencia_activa_total=PotenciaActiva(61500.0),
        potencia_reactiva_total=PotenciaReactiva(-42800.0),
        potencia_aparente_total=PotenciaAparente(74900.0),
        factor_potencia_total=FactorPotencia(0.82),
    )


def test_supresion_alertas_fp_cuando_hay_tis_duplicados():
    ProcesadorAlertasIngesta.limpiar_estado()
    dispositivo = _crear_dispositivo_constituyentes()
    lectura = _crear_lectura_con_ti_duplicado()
    ahora = datetime.now(timezone.utc)

    repo_mock = MagicMock()
    pub_mock = MagicMock()
    logger_mock = MagicMock()

    # Lectura 1: registra anomalía en ventana
    ProcesadorAlertasIngesta.procesar_alertas(
        dispositivo=dispositivo,
        mac_raw="D4:8C:49:F0:35:A8",
        lectura=lectura,
        recorded_at=ahora,
        repo_telemetria=repo_mock,
        publicador=pub_mock,
        logger=logger_mock,
    )

    # Lectura 2: persistencia confirmada
    ProcesadorAlertasIngesta.procesar_alertas(
        dispositivo=dispositivo,
        mac_raw="D4:8C:49:F0:35:A8",
        lectura=lectura,
        recorded_at=ahora + timedelta(seconds=4),
        repo_telemetria=repo_mock,
        publicador=pub_mock,
        logger=logger_mock,
    )

    alertas_guardadas = [args[0][0].tipo_alerta for args in repo_mock.guardar_alerta.call_args_list]

    # Debe alertar la anomalía física de TIs
    assert any("TI" in t for t in alertas_guardadas)

    # NO debe alertar BAJO_FACTOR_POTENCIA ni SOBRECOMPENSACION_REACTIVA porque están suprimidas
    assert "BAJO_FACTOR_POTENCIA" not in alertas_guardadas
    assert "SOBRECOMPENSACION_REACTIVA" not in alertas_guardadas
