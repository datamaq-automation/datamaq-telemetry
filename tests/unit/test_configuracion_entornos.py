"""tests/unit/test_configuracion_entornos.py — Modos de entorno (APP_ENV): derivación de postura dev/prod y regresión de arquitectura."""

import ast
from pathlib import Path

import pydantic
import pytest

from src.infrastructure.settings.config import Settings

_CLAVES_ENV = [
    "APP_ENV",
    "DEBUG",
    "API_EXPOSE_DOCS",
    "CORS_ORIGINS",
    "LOG_FORMAT",
    "LOG_LEVEL",
    "API_SECRET_KEY",
    "OTP_HMAC_KEY",
    "DB_PASSWORD",
    "AUTH_REQUIRED",
    "LOGIN_MAX_INTENTOS",
    "LOGIN_VENTANA_SEGUNDOS",
]


def _build(monkeypatch, **overrides) -> Settings:
    for clave in _CLAVES_ENV:
        monkeypatch.delenv(clave, raising=False)
    # Producción exige OTP_HMAC_KEY propia (ver test_otp_hmac_key_config.py).
    overrides.setdefault("OTP_HMAC_KEY", "clave-otp-de-prueba-0123456789")
    return Settings(_env_file=None, **overrides)


# P1 — DEBUG=True es opt-in canónico a development (coacción, sin error)
def test_debug_true_coacciona_a_development(monkeypatch):
    settings = _build(monkeypatch, DEBUG=True)
    assert settings.APP_ENV == "development"
    assert settings.DEBUG is True


# P1b — producción por defecto y DEBUG derivado False
def test_produccion_por_defecto_debug_false(monkeypatch):
    settings = _build(monkeypatch, API_SECRET_KEY="secreto-fuerte-123456", DB_PASSWORD="clave-segura")
    assert settings.APP_ENV == "production"
    assert settings.DEBUG is False


# P2 — defaults de development
def test_development_deriva_defaults_dev(monkeypatch):
    settings = _build(monkeypatch, APP_ENV="development")
    assert settings.DEBUG is True
    assert settings.LOG_FORMAT == "console"
    assert settings.LOG_LEVEL == "DEBUG"
    assert settings.API_EXPOSE_DOCS is True
    assert settings.CORS_ORIGINS == "http://localhost:5173"


# P3 — producción exige secreto fuerte
def test_produccion_rechaza_secreto_debil(monkeypatch):
    with pytest.raises(pydantic.ValidationError):
        _build(monkeypatch, APP_ENV="production", API_SECRET_KEY="corta")


# P4 — defaults de production
def test_production_deriva_defaults_prod(monkeypatch):
    settings = _build(
        monkeypatch,
        APP_ENV="production",
        API_SECRET_KEY="secreto-fuerte-123456",
        DB_PASSWORD="clave-segura",
    )
    assert settings.LOG_FORMAT == "json"
    assert settings.LOG_LEVEL == "INFO"
    assert settings.API_EXPOSE_DOCS is False
    assert settings.CORS_ORIGINS == ""


# P5 — override explícito gana sobre el default del perfil
def test_override_explicito_gana(monkeypatch):
    settings = _build(monkeypatch, APP_ENV="development", LOG_FORMAT="json")
    assert settings.LOG_FORMAT == "json"


# P6 — arquitectura: domain/ y application/ no importan infrastructure
def test_capas_internas_no_importan_infrastructure():
    raiz = Path(__file__).resolve().parents[2] / "src"
    infracciones: list[str] = []
    for carpeta in ("domain", "application"):
        for archivo in (raiz / carpeta).rglob("*.py"):
            tree = ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))
            for nodo in ast.walk(tree):
                if isinstance(nodo, ast.ImportFrom) and nodo.module and "infrastructure" in nodo.module:
                    infracciones.append(f"{archivo}: from {nodo.module}")
                elif isinstance(nodo, ast.Import):
                    for alias in nodo.names:
                        if "infrastructure" in alias.name:
                            infracciones.append(f"{archivo}: import {alias.name}")
    assert not infracciones, f"Capas internas importan infrastructure: {infracciones}"
