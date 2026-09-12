"""tests/unit/test_ingestar_automate.py."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.application.use_cases.ingesta.ingestar_automate import (
    CalculadorCadenciaProduccionService,
    IngestarAutomateUseCase,
)
from src.domain.telemetria.entities import Dispositivo
from src.domain.telemetria.value_objects import MacAddress
from src.infrastructure.settings.config import Settings


def test_settings_topic_prefixes_parsing():
    settings = Settings(MQTT_TOPIC_PREFIX="m/wifi/#,auto24v4m/#")
    assert settings.topic_prefixes == ["m/wifi/#", "auto24v4m/#"]


def test_calculador_cadencia_produccion_ppm():
    service = CalculadorCadenciaProduccionService(umbral_marcha_ppm=30.0)
    dev_id = "AUT24V4M001"

    # Simular 35 impulsos recibidos a lo largo de un minuto
    for i in range(35):
        ts = datetime(2026, 9, 11, 10, 0, i, tzinfo=timezone.utc)
        ppm = service.registrar_impulso(dev_id, timestamp=ts)

    assert ppm >= 30.0
    assert service.determinar_estado(ppm) == "MARCHA"


def test_calculador_cadencia_produccion_parada():
    service = CalculadorCadenciaProduccionService(umbral_marcha_ppm=30.0)
    dev_id = "AUT24V4M001"

    # Simular solo 5 impulsos en un minuto
    for i in range(5):
        ts = datetime(2026, 9, 11, 10, 0, i * 10, tzinfo=timezone.utc)
        ppm = service.registrar_impulso(dev_id, timestamp=ts)

    assert ppm < 30.0
    assert service.determinar_estado(ppm) == "PARADA"


def test_ingestar_automate_use_case_procesar_io_dict():
    repo_disp = MagicMock()
    use_case_disponibilidad = MagicMock()

    # Retorna dispositivo existente
    disp = Dispositivo(
        id="dev-aut-1",
        device_uid=MacAddress("AABBCCDDEEFF"),
        nombre="Automate-EEFF",
        modelo="Automate24V4M",
    )
    repo_disp.obtener_por_uid.return_value = disp

    use_case = IngestarAutomateUseCase(
        repo_dispositivos=repo_disp,
        disponibilidad_use_case=use_case_disponibilidad,
        permitir_auto_registro=True,
    )

    topico = "auto24v4m/AABBCCDDEEFF/inst/io/v1"
    payload = {"id": 1, "t": "2026-09-11T10:00:00Z", "v": 1}

    use_case.ejecutar(topico, payload)
    repo_disp.actualizar_heartbeat.assert_called()


def test_ingestar_automate_use_case_procesar_io_lista():
    repo_disp = MagicMock()
    use_case_disponibilidad = MagicMock()

    disp = Dispositivo(
        id="dev-aut-1",
        device_uid=MacAddress("AABBCCDDEEFF"),
        nombre="Automate-EEFF",
        modelo="Automate24V4M",
    )
    repo_disp.obtener_por_uid.return_value = disp

    use_case = IngestarAutomateUseCase(
        repo_dispositivos=repo_disp,
        disponibilidad_use_case=use_case_disponibilidad,
        permitir_auto_registro=True,
    )

    topico = "auto24v4m/AABBCCDDEEFF/inst/io/v1"
    payload = [
        {"id": 1, "t": "2026-09-11T10:00:00Z", "v": 1},
        {"id": 2, "t": "2026-09-11T10:00:00Z", "v": 0},
    ]

    use_case.ejecutar(topico, payload)
    repo_disp.actualizar_heartbeat.assert_called()
