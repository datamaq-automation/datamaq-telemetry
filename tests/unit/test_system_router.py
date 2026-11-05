"""tests/unit/test_system_router.py — Tests para system_router y endpoints de health check (Issue #144)."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.infrastructure.fastapi.server import create_app


def _cliente_con_sistema_saludable():
    app = create_app()
    return TestClient(app)


@patch("src.infrastructure.fastapi.routes.system_router._validar_datamaq_data", return_value={"valido": True})
@patch(
    "src.infrastructure.fastapi.routes.system_router.verificar_estado_migraciones", return_value={"sincronizado": True}
)
@patch("src.infrastructure.fastapi.routes.system_router.verificar_conexion_db", return_value=True)
@patch("src.infrastructure.fastapi.routes.system_router.get_mqtt_listener")
def test_head_health_retorna_200_body_vacio(mock_listener, mock_db, mock_migr, mock_data):
    """HEAD /health responde HTTP 200 con cuerpo vacío y cabeceras equivalentes a GET (#144)."""
    mock_l = MagicMock()
    mock_l.esta_conectado.return_value = True
    mock_listener.return_value = mock_l

    client = _cliente_con_sistema_saludable()
    response = client.head("/health")

    assert response.status_code == 200
    assert response.content == b""
    assert response.text == ""
    assert "application/json" in response.headers.get("content-type", "")


@patch("src.infrastructure.fastapi.routes.system_router._validar_datamaq_data", return_value={"valido": True})
@patch(
    "src.infrastructure.fastapi.routes.system_router.verificar_estado_migraciones", return_value={"sincronizado": True}
)
@patch("src.infrastructure.fastapi.routes.system_router.verificar_conexion_db", return_value=True)
@patch("src.infrastructure.fastapi.routes.system_router.get_mqtt_listener")
def test_head_health_ready_retorna_200_body_vacio(mock_listener, mock_db, mock_migr, mock_data):
    """HEAD /health/ready responde HTTP 200 con cuerpo vacío y cabeceras equivalentes a GET (#144)."""
    mock_l = MagicMock()
    mock_l.esta_conectado.return_value = True
    mock_listener.return_value = mock_l

    client = _cliente_con_sistema_saludable()
    response = client.head("/health/ready")

    assert response.status_code == 200
    assert response.content == b""
    assert response.text == ""
    assert "application/json" in response.headers.get("content-type", "")


def test_head_health_live_retorna_200_body_vacio():
    """HEAD /health/live responde HTTP 200 con cuerpo vacío y cabeceras equivalentes a GET (#144)."""
    client = _cliente_con_sistema_saludable()
    response = client.head("/health/live")

    assert response.status_code == 200
    assert response.content == b""
    assert response.text == ""
    assert "application/json" in response.headers.get("content-type", "")


def test_get_health_live_retorna_200_con_json():
    """GET /health/live sigue retornando JSON válido con status alive."""
    client = _cliente_con_sistema_saludable()
    response = client.get("/health/live")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"
    assert "timestamp" in data
