"""Fase 1 — Hardening de configuración (postura segura por defecto)."""

import pydantic

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
    "API_EXPOSE_DOCS",
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


def test_debug_default_false(monkeypatch):
    assert Settings.model_fields["DEBUG"].default is False


def test_api_host_default_loopback(monkeypatch):
    assert Settings.model_fields["API_HOST"].default == "127.0.0.1"


def test_cors_default_vacio(monkeypatch):
    assert Settings.model_fields["CORS_ORIGINS"].default == ""


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
