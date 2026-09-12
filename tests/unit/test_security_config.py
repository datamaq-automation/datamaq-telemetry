"""tests/unit/test_security_config.py — Hardening de configuración (postura segura por defecto)."""

from pathlib import Path

import pydantic
import pytest

from src.infrastructure.settings.config import Settings

_CLAVES_ENV = [
    "DB_HOST",
    "DB_PORT",
    "DB_USER",
    "DB_PASSWORD",
    "DB_NAME",
    "MQTT_BROKER_HOST",
    "MQTT_BROKER_PORT",
    "MQTT_USERNAME",
    "MQTT_PASSWORD",
    "MQTT_CLIENT_ID",
    "MQTT_TOPIC_PREFIX",
    "MQTT_TLS_ENABLED",
    "MQTT_TLS_CA_CERTS",
    "MQTT_MAX_PAYLOAD_BYTES",
    "MQTT_AUTO_REGISTER_DEVICES",
    "API_HOST",
    "API_PORT",
    "API_SECRET_KEY",
    "AUTH_TOKEN_EXPIRA_MINUTOS",
    "AUTH_REQUIRED",
    "AUTH_COOKIE_NOMBRE",
    "AUTH_COOKIE_HTTPONLY",
    "AUTH_COOKIE_SAMESITE",
    "API_EXPOSE_DOCS",
    "APP_ENV",
    "DEBUG",
    "CORS_ORIGINS",
    "LOGIN_MAX_INTENTOS",
    "LOGIN_VENTANA_SEGUNDOS",
    "LOG_FORMAT",
    "LOG_LEVEL",
]


def _settings(monkeypatch, **overrides):
    for clave in _CLAVES_ENV:
        monkeypatch.delenv(clave, raising=False)
    return Settings(_env_file=None, **overrides)


def test_modo_produccion_por_defecto_debug_false(monkeypatch):
    settings = _settings(monkeypatch, API_SECRET_KEY="secreto-fuerte-123456", DB_PASSWORD="clave-segura")
    assert settings.APP_ENV == "production"
    assert settings.DEBUG is False


def test_api_host_default_loopback(monkeypatch):
    assert Settings.model_fields["API_HOST"].default == "127.0.0.1"


def test_cors_vacio_en_produccion(monkeypatch):
    settings = _settings(monkeypatch, API_SECRET_KEY="secreto-fuerte-123456", DB_PASSWORD="clave-segura")
    assert settings.CORS_ORIGINS == ""


def test_secret_key_default_vacia(monkeypatch):
    assert Settings.model_fields["API_SECRET_KEY"].default == ""


def test_token_expiracion_corta_default(monkeypatch):
    assert Settings.model_fields["AUTH_TOKEN_EXPIRA_MINUTOS"].default <= 120


def test_auth_required_default_true(monkeypatch):
    assert Settings.model_fields["AUTH_REQUIRED"].default is True


def test_produccion_rechaza_secreto_debil(monkeypatch):
    try:
        _settings(monkeypatch, DEBUG=False, API_SECRET_KEY="dev-secret-key-datamaq", DB_PASSWORD="x")
        raise AssertionError("Se esperaba ValidationError")
    except pydantic.ValidationError:
        pass


def test_produccion_rechaza_db_password_vacia(monkeypatch):
    try:
        _settings(monkeypatch, DEBUG=False, API_SECRET_KEY="secreto-fuerte-123456", DB_PASSWORD="")
        raise AssertionError("Se esperaba ValidationError")
    except pydantic.ValidationError:
        pass


def test_dev_autogenera_secreto_vacio(monkeypatch):
    settings = _settings(monkeypatch, DEBUG=True)
    assert settings.API_SECRET_KEY != ""
    assert len(settings.API_SECRET_KEY) >= 32


def test_cookie_nombre_default():
    assert Settings.model_fields["AUTH_COOKIE_NOMBRE"].default == "datamaq_token"


def test_cookie_httponly_default_true():
    assert Settings.model_fields["AUTH_COOKIE_HTTPONLY"].default is True


def test_cookie_samesite_default_strict():
    assert Settings.model_fields["AUTH_COOKIE_SAMESITE"].default == "strict"


def test_cookie_secure_desactivada_en_dev(monkeypatch):
    settings = _settings(monkeypatch, DEBUG=True)
    assert settings.auth_cookie_secure is False


def test_cookie_secure_activada_en_produccion(monkeypatch):
    settings = _settings(
        monkeypatch,
        DEBUG=False,
        API_SECRET_KEY="secreto-fuerte-123456",
        DB_PASSWORD="clave-segura",
    )
    assert settings.auth_cookie_secure is True


def test_cookie_max_age_deriva_de_expiracion(monkeypatch):
    settings = _settings(monkeypatch, DEBUG=True, AUTH_TOKEN_EXPIRA_MINUTOS=480)
    assert settings.auth_cookie_max_age == 28800


def test_produccion_rechaza_auth_requerida_false(monkeypatch):
    with pytest.raises(ValueError):
        _settings(
            monkeypatch,
            DEBUG=False,
            AUTH_REQUIRED=False,
            API_SECRET_KEY="clave-secreta-fuerte-123",
            DB_PASSWORD="clave-db-fuerte-123",
        )


def test_produccion_acepta_auth_requerida_true(monkeypatch):
    settings = _settings(
        monkeypatch,
        DEBUG=False,
        AUTH_REQUIRED=True,
        API_SECRET_KEY="clave-secreta-fuerte-123",
        DB_PASSWORD="clave-db-fuerte-123",
    )
    assert settings.AUTH_REQUIRED is True


def test_env_example_es_seguro():
    ruta = Path(__file__).resolve().parents[2] / ".env.example"
    contenido = ruta.read_text(encoding="utf-8")
    assert "CORS_ORIGINS=*" not in contenido
    assert "DEBUG=False" in contenido
    assert "AUTH_REQUIRED=True" in contenido
