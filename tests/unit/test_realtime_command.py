"""tests/unit/test_realtime_command.py."""
from unittest.mock import MagicMock, patch

from starlette.testclient import TestClient

from src.infrastructure.fastapi.dependencies import registrar_mqtt_listener
from src.infrastructure.fastapi.server import (
    _renovar_modo_tiempo_real_medidores,
    create_app,
)
from src.infrastructure.paho_mqtt.mqtt_listener import MQTTListener


def test_activar_tiempo_real_dispositivo_publica_comando():
    listener = MQTTListener.__new__(MQTTListener)
    listener._esta_conectado = True
    listener.client = MagicMock()
    listener.settings = MagicMock()

    mock_info = MagicMock()
    listener.client.publish.return_value = mock_info

    resultado = listener.activar_tiempo_real_dispositivo("D48C49F03564", segundos=90)
    assert resultado is True
    listener.client.publish.assert_called_once()
    args, _ = listener.client.publish.call_args
    topico, payload_str = args
    assert topico == "m/wifi/D48C49F03564/conf/com"
    assert '"set": "realtime_sync_mode"' in payload_str
    assert '"time_s": 90' in payload_str


def test_endpoint_activar_tiempo_real():
    mock_listener = MagicMock()
    mock_listener.esta_conectado.return_value = True
    mock_listener.activar_tiempo_real_dispositivo.return_value = True
    registrar_mqtt_listener(mock_listener)

    from src.infrastructure.fastapi.dependencies import (
        get_dispositivos_use_case,
        get_usuario_actual,
    )

    app = create_app()
    mock_uc = MagicMock()
    mock_disp = MagicMock()
    mock_disp.id = "disp-1"
    mock_disp.device_uid = "D48C49F03564"
    mock_uc.obtener_dispositivo.return_value = mock_disp

    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "user-test", "rol": "operador"}
    app.dependency_overrides[get_dispositivos_use_case] = lambda: mock_uc

    client = TestClient(app)
    resp = client.post("/api/v1/dispositivos/disp-1/realtime?segundos=120")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["tiempo_real_activado"] is True
    assert data["device_uid"] == "D48C49F03564"


def test_renovar_modo_tiempo_real_medidores_itera_dispositivos():
    mock_listener = MagicMock()
    mock_listener.esta_conectado.return_value = True

    mock_db = MagicMock()
    mock_repo = MagicMock()
    mock_disp = MagicMock()
    mock_disp.device_uid.valor = "AABBCCDDEEFF"
    mock_repo.listar.return_value = [mock_disp]

    with (
        patch("src.infrastructure.fastapi.server.get_session_factory", return_value=lambda: mock_db),
        patch("src.infrastructure.fastapi.server.MySQLDispositivosRepository", return_value=mock_repo),
    ):
        _renovar_modo_tiempo_real_medidores(mock_listener)

        mock_listener.activar_tiempo_real_dispositivo.assert_called_once_with("AABBCCDDEEFF", segundos=120)
