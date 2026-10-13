"""CORS y cookie de sesión para app-dev.datamaq.com.ar (T1 a T6 de spec-cors-app-dev.md).

Patrón igual a tests/unit/test_cors_cybersyn.py. Los tests de WebSocket (T7 a T9) quedan
pendientes hasta que el dueño decida C4 (validación de Origin en /ws/live).
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

ORIGEN_DEV = "https://app-dev.datamaq.com.ar"
ORIGEN_PROD = "https://app.datamaq.com.ar"
AHORA = datetime.now(timezone.utc)
CLAVE = "clave-de-prueba-api-dev-0123456789abcdef"


def _settings_dev_api(cors_origins: str = ORIGEN_DEV) -> Settings:
    """Perfil de api-dev: APP_ENV=production y DEBUG=false (D3), CORS con el origen de dev por env."""
    return Settings(
        APP_ENV="production",
        DEBUG=False,
        API_SECRET_KEY=CLAVE,
        CORS_ORIGINS=cors_origins,
        AUTH_COOKIE_SAMESITE="strict",
        MQTT_HABILITADO=False,
    )


def _cliente(settings: Settings) -> TestClient:
    auth = MagicMock()
    auth.login.return_value = LoginResponseDTO(token="token_jwt_prueba", expira_en=AHORA)
    app = create_app(settings=settings)
    app.dependency_overrides[get_settings_dep] = lambda: settings
    app.dependency_overrides[get_auth_use_case] = lambda: auth
    return TestClient(app)


def _preflight(cliente: TestClient, origen: str):
    return cliente.options(
        "/api/v1/auth/login",
        headers={
            "Origin": origen,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )


@pytest.fixture
def cliente_dev() -> TestClient:
    return _cliente(_settings_dev_api())


# T1: el origen de dev se permite con credenciales.
def test_t1_preflight_origen_dev_permitido_con_credenciales(cliente_dev: TestClient) -> None:
    respuesta = _preflight(cliente_dev, ORIGEN_DEV)
    assert respuesta.status_code == 200
    assert respuesta.headers.get("access-control-allow-origin") == ORIGEN_DEV
    assert respuesta.headers.get("access-control-allow-credentials") == "true"


# T2: producción sin dev en CORS_ORIGINS no permite el origen de dev.
def test_t2_produccion_sin_origen_dev_lo_rechaza() -> None:
    cliente_prod = _cliente(_settings_dev_api(cors_origins=""))
    respuesta = _preflight(cliente_prod, ORIGEN_DEV)
    assert respuesta.headers.get("access-control-allow-origin") != ORIGEN_DEV


# T3: la config de dev no abre el origen de producción.
def test_t3_config_dev_no_abre_origen_produccion(cliente_dev: TestClient) -> None:
    respuesta = _preflight(cliente_dev, ORIGEN_PROD)
    assert respuesta.headers.get("access-control-allow-origin") != ORIGEN_PROD


# T4: Cybersyn sigue permitido (regresión).
def test_t4_cybersyn_sigue_permitido(cliente_dev: TestClient) -> None:
    respuesta = _preflight(cliente_dev, "https://cybersyn.com.ar")
    assert respuesta.headers.get("access-control-allow-origin") == "https://cybersyn.com.ar"


# T5: el comodín '*' no se acepta fuera de DEBUG.
def test_t5_comodin_rechazado_fuera_de_debug() -> None:
    with pytest.raises(ValueError):
        _settings_dev_api(cors_origins="*")


# T6: login desde app-dev: cookie host-only, HttpOnly, SameSite=strict, Secure (DEBUG=false), sin Domain.
def test_t6_cookie_login_host_only_y_secure(cliente_dev: TestClient) -> None:
    respuesta = cliente_dev.post(
        "/api/v1/auth/login",
        json={"usuario": "admin@datamaq.com.ar", "contrasena": "SecretPassword123"},
        headers={"Origin": ORIGEN_DEV},
    )
    assert respuesta.status_code == 200
    cookie = respuesta.headers.get("set-cookie", "")
    assert "datamaq_token=token_jwt_prueba" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Secure" in cookie
    assert "Domain=" not in cookie
