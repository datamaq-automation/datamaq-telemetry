"""Pruebas unitarias de CORS y emisión de cookies de sesión para el origen Cybersyn.

Verifica:
1. Allow-list de CORS para https://cybersyn.com.ar y https://www.cybersyn.com.ar.
2. Rechazo de CORS para https://synco.com.ar.
3. Emisión de cookies HttpOnly con SameSite=None; Secure ante peticiones de Cybersyn.
4. Preservación del comportamiento estricto nativo (*.datamaq.com.ar o sin origin).
5. Eliminación de cookies en logout con atributos compatibles cross-site.
6. Prohibición de comodín '*' en producción.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.application.dtos.auth_dto import LoginResponseDTO
from src.infrastructure.fastapi.auth_dependencies import (
    get_auth_use_case,
    get_verificar_2fa_use_case,
)
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
def mock_auth_use_case():
    mock = MagicMock()
    mock.login.return_value = LoginResponseDTO(
        token="token_jwt_prueba",
        expira_en=AHORA,
    )
    mock.guest.return_value = LoginResponseDTO(
        token="token_jwt_guest",
        expira_en=AHORA,
    )
    return mock


@pytest.fixture
def mock_2fa_use_case():
    mock = MagicMock()
    mock.verificar.return_value = LoginResponseDTO(
        token="token_jwt_2fa",
        expira_en=AHORA,
        device_trust_token="token_trust_device",
    )
    return mock


@pytest.fixture
def client(settings_dev, mock_auth_use_case, mock_2fa_use_case):
    app = create_app(settings=settings_dev)
    app.dependency_overrides[get_settings_dep] = lambda: settings_dev
    app.dependency_overrides[get_auth_use_case] = lambda: mock_auth_use_case
    app.dependency_overrides[get_verificar_2fa_use_case] = lambda: mock_2fa_use_case
    return TestClient(app)


# ==============================================================================
# 1. ALLOW-LIST DE CORS
# ==============================================================================


def test_cors_options_cybersyn_permitido(client):
    response = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "https://cybersyn.com.ar",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://cybersyn.com.ar"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_options_www_cybersyn_permitido(client):
    response = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "https://www.cybersyn.com.ar",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://www.cybersyn.com.ar"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_options_app_cybersyn_permitido(client):
    response = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "https://app.cybersyn.com.ar",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://app.cybersyn.com.ar"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_options_synco_rechazado(client):
    response = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "https://synco.com.ar",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    # Origen no permitido por CORS: CORSMiddleware no emite Access-Control-Allow-Origin
    assert response.headers.get("access-control-allow-origin") != "https://synco.com.ar"


# ==============================================================================
# 2. EMISIÓN DE COOKIES ADAPTATIVAS (SameSite / Secure)
# ==============================================================================


def test_login_cookie_cybersyn_samesite_none_secure(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"usuario": "admin@cybersyn.com.ar", "contrasena": "SecretPassword123"},
        headers={"Origin": "https://cybersyn.com.ar"},
    )
    assert response.status_code == 200
    cookie_header = response.headers.get("set-cookie", "")
    assert "datamaq_token=token_jwt_prueba" in cookie_header
    assert "HttpOnly" in cookie_header
    assert "SameSite=none" in cookie_header
    assert "Secure" in cookie_header


def test_login_cookie_www_cybersyn_samesite_none_secure(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"usuario": "admin@cybersyn.com.ar", "contrasena": "SecretPassword123"},
        headers={"Origin": "https://www.cybersyn.com.ar"},
    )
    assert response.status_code == 200
    cookie_header = response.headers.get("set-cookie", "")
    assert "SameSite=none" in cookie_header
    assert "Secure" in cookie_header


def test_login_cookie_app_cybersyn_samesite_none_secure(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"usuario": "admin@cybersyn.com.ar", "contrasena": "SecretPassword123"},
        headers={"Origin": "https://app.cybersyn.com.ar"},
    )
    assert response.status_code == 200
    cookie_header = response.headers.get("set-cookie", "")
    assert "SameSite=none" in cookie_header
    assert "Secure" in cookie_header


def test_login_cookie_referer_cybersyn_samesite_none_secure(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"usuario": "admin@cybersyn.com.ar", "contrasena": "SecretPassword123"},
        headers={"Referer": "https://cybersyn.com.ar/dashboard"},
    )
    assert response.status_code == 200
    cookie_header = response.headers.get("set-cookie", "")
    assert "SameSite=none" in cookie_header
    assert "Secure" in cookie_header


def test_login_cookie_datamaq_nativo_preserva_strict(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"usuario": "admin@datamaq.com.ar", "contrasena": "SecretPassword123"},
        headers={"Origin": "https://app.datamaq.com.ar"},
    )
    assert response.status_code == 200
    cookie_header = response.headers.get("set-cookie", "")
    assert "SameSite=strict" in cookie_header
    assert "SameSite=none" not in cookie_header


def test_login_cookie_sin_origin_preserva_strict(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"usuario": "admin@datamaq.com.ar", "contrasena": "SecretPassword123"},
    )
    assert response.status_code == 200
    cookie_header = response.headers.get("set-cookie", "")
    assert "SameSite=strict" in cookie_header
    assert "SameSite=none" not in cookie_header


def test_login_cookie_synco_no_recibe_samesite_none(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"usuario": "admin@synco.com.ar", "contrasena": "SecretPassword123"},
        headers={"Origin": "https://synco.com.ar"},
    )
    assert response.status_code == 200
    cookie_header = response.headers.get("set-cookie", "")
    assert "SameSite=strict" in cookie_header
    assert "SameSite=none" not in cookie_header


def test_guest_cookie_cybersyn_samesite_none_secure(client):
    response = client.post(
        "/api/v1/auth/guest",
        headers={"Origin": "https://cybersyn.com.ar"},
    )
    assert response.status_code == 200
    cookie_header = response.headers.get("set-cookie", "")
    assert "datamaq_token=token_jwt_guest" in cookie_header
    assert "SameSite=none" in cookie_header
    assert "Secure" in cookie_header


def test_logout_cookie_cybersyn_samesite_none_secure(client):
    response = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "https://cybersyn.com.ar"},
    )
    assert response.status_code == 200
    cookie_header = response.headers.get("set-cookie", "")
    assert "datamaq_token=" in cookie_header
    assert "SameSite=none" in cookie_header
    assert "Secure" in cookie_header


def test_verificar_2fa_cookie_cybersyn_samesite_none_secure(client):
    response = client.post(
        "/api/v1/auth/2fa/verificar",
        json={"mfa_token": "mfa-temp-token", "codigo": "123456", "recordar_dispositivo": True},
        headers={"Origin": "https://cybersyn.com.ar"},
    )
    assert response.status_code == 200
    cookie_headers = response.headers.get_list("set-cookie")
    cookie_str = " ".join(cookie_headers)
    assert "datamaq_token=token_jwt_2fa" in cookie_str
    assert "datamaq_device_trust=token_trust_device" in cookie_str
    assert "SameSite=none" in cookie_str
    assert "Secure" in cookie_str


# ==============================================================================
# 3. SEGURIDAD Y CONFIGURACIÓN EN PRODUCCIÓN
# ==============================================================================


def test_servidor_rechaza_cors_asterisco_en_produccion():
    settings_prod_invalido = Settings(
        APP_ENV="production",
        DEBUG=False,
        API_SECRET_KEY="secreto-fuerte-123456",
        OTP_HMAC_KEY="clave-otp-de-prueba-0123456789",
        DB_PASSWORD="clave-segura-prod",
    )
    object.__setattr__(settings_prod_invalido, "CORS_ORIGINS", "*")
    with pytest.raises(ValueError, match=r"CORS_ORIGINS no puede ser '\*' en producción"):
        create_app(settings=settings_prod_invalido)
