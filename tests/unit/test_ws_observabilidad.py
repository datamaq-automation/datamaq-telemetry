"""tests/unit/test_ws_observabilidad.py."""

from unittest.mock import patch

from starlette.testclient import TestClient

from src.infrastructure.fastapi.dependencies import requiere_rol_superadmin
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
    app.dependency_overrides[requiere_rol_superadmin] = lambda: {"sub": "u-super", "rol": "superadmin"}
    client = TestClient(app)
    response = client.get("/api/v1/system/ws-status")
    assert response.status_code == 200
    data = response.json()
    assert "clientes_activos" in data
    assert "total_broadcasts" in data
    assert "mqtt_conectado" in data


def test_endpoint_ws_status_anonimo_rechazado_401():
    app = create_app()
    client = TestClient(app)
    response = client.get("/api/v1/system/ws-status")
    assert response.status_code == 401


def test_broadcast_sin_clientes_loguea_info():
    with patch("src.infrastructure.fastapi.server.logger") as mock_logger:
        websocket_broadcast_callback("m/wifi/TEST/inst", {"potencia": 123})
        eventos = [call.args[0] for call in mock_logger.info.call_args_list if call.args]
        assert "ws_broadcast_sin_clientes" in eventos


def test_validar_datamaq_data_excepcion_loguea_error():
    from src.infrastructure.fastapi.routes.system_router import _validar_datamaq_data

    with (
        patch(
            "src.infrastructure.fastapi.routes.system_router.cargar_organizaciones_completas",
            side_effect=RuntimeError("fallo al cargar yaml"),
        ),
        patch("src.infrastructure.fastapi.routes.system_router.logger") as mock_logger,
        patch("os.path.isdir", return_value=True),
    ):
        res = _validar_datamaq_data()
        assert res == {"valido": False, "razon": "error_interno_validacion"}
        mock_logger.error.assert_called_once_with("error_validacion_datamaq_data", exc_info=True)
