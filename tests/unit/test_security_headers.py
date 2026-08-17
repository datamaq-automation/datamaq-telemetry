"""Fase G4 — Middleware de headers de seguridad en toda respuesta."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.infrastructure.fastapi.security_headers import SecurityHeadersMiddleware
from src.infrastructure.settings.config import Settings


def _app_con_headers(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    return app


def _settings_prod() -> Settings:
    return Settings(
        _env_file=None,
        DEBUG=False,
        API_SECRET_KEY="secreto-fuerte-123456",
        DB_PASSWORD="clave-segura",
    )


def _settings_dev() -> Settings:
    return Settings(_env_file=None, DEBUG=True)


def test_headers_basicos_presentes():
    client = TestClient(_app_con_headers(_settings_prod()))
    respuesta = client.get("/ping")

    assert respuesta.headers["X-Content-Type-Options"] == "nosniff"
    assert respuesta.headers["X-Frame-Options"] == "DENY"
    assert respuesta.headers["Referrer-Policy"] == "no-referrer"


def test_hsts_presente_en_produccion():
    client = TestClient(_app_con_headers(_settings_prod()))
    respuesta = client.get("/ping")

    assert respuesta.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"


def test_hsts_ausente_en_debug():
    client = TestClient(_app_con_headers(_settings_dev()))
    respuesta = client.get("/ping")

    assert "Strict-Transport-Security" not in respuesta.headers


def test_csp_ausente_si_header_vacio():
    client = TestClient(_app_con_headers(_settings_prod()))
    respuesta = client.get("/ping")

    assert "Content-Security-Policy" not in respuesta.headers


def test_csp_presente_si_configurado():
    settings = Settings(_env_file=None, DEBUG=True, CSP_HEADER="default-src 'self'")
    client = TestClient(_app_con_headers(settings))
    respuesta = client.get("/ping")

    assert respuesta.headers["Content-Security-Policy"] == "default-src 'self'"
