"""tests/unit/test_cors_request_id.py.

X-Request-ID debe poder leerse desde JavaScript en peticiones cross-origin.

El middleware ya emite el header en todas las respuestas; CORS solo lo expone si está
en expose_headers. El frontend lo necesita para mostrar el id en los errores (app-datamaq#29).
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.application.dtos.auth_dto import LoginResponseDTO
from src.infrastructure.fastapi.auth_dependencies import get_auth_use_case
from src.infrastructure.fastapi.dependencies import get_settings_dep
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.settings.config import Settings

AHORA = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def settings_dev():
    return Settings(
        APP_ENV="development",
        DEBUG=True,
        API_SECRET_KEY="dev-secret-key-12345",
        CORS_ORIGINS="",
        AUTH_COOKIE_SAMESITE="strict",
    )


@pytest.fixture
def client(settings_dev):
    mock_auth = MagicMock()
    mock_auth.login.return_value = LoginResponseDTO(token="token_jwt_prueba", expira_en=AHORA)
    app = create_app(settings=settings_dev)
    app.dependency_overrides[get_settings_dep] = lambda: settings_dev
    app.dependency_overrides[get_auth_use_case] = lambda: mock_auth
    return TestClient(app)


def test_request_id_llega_en_respuesta_cross_origin(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"usuario": "admin@datamaq.com.ar", "contrasena": "SecretPassword123"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.headers.get("x-request-id")


def test_request_id_se_expone_a_cors(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"usuario": "admin@datamaq.com.ar", "contrasena": "SecretPassword123"},
        headers={"Origin": "http://localhost:5173"},
    )
    expuestos = response.headers.get("access-control-expose-headers", "")
    assert "X-Request-ID" in expuestos


def test_request_id_se_expone_en_get_con_origin_permitido(client):
    """Issue datamaq-automation/datamaq#64: una respuesta GET con Origin permitido
    debe incluir X-Request-ID en Access-Control-Expose-Headers.
    """
    response = client.get(
        "/health/build",
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 200
    expuestos = response.headers.get("access-control-expose-headers", "")
    assert "X-Request-ID" in expuestos
    assert response.headers.get("x-request-id")
