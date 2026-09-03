from unittest.mock import patch

from starlette.testclient import TestClient

from src.infrastructure.fastapi.server import (
    create_app,
    obtener_metricas_ws,
    websocket_broadcast_callback,
)


def test_metricas_ws_inicial():
    metricas = obtener_metricas_ws()
    assert "clientes_activos" in metricas
    assert "total_conexiones" in metricas
    assert "total_broadcasts" in metricas
    assert "ultimo_broadcast_en" in metricas
    assert isinstance(metricas["clientes_activos"], int)


def test_endpoint_ws_status():
    app = create_app()
    client = TestClient(app)
    response = client.get("/api/v1/system/ws-status")
    assert response.status_code == 200
    data = response.json()
    assert "clientes_activos" in data
    assert "total_broadcasts" in data
    assert "mqtt_conectado" in data


def test_broadcast_sin_clientes_loguea_info():
    with patch("src.infrastructure.fastapi.server.logger") as mock_logger:
        websocket_broadcast_callback("m/wifi/TEST/inst", {"potencia": 123})
        eventos = [call.args[0] for call in mock_logger.info.call_args_list if call.args]
        assert "ws_broadcast_sin_clientes" in eventos
