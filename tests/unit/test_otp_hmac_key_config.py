"""tests/unit/test_otp_hmac_key_config.py — Clave dedicada para firmar los OTP de cambio de contraseña."""

import pytest

from src.infrastructure.settings.config import Settings

_BASE_PROD = {"API_SECRET_KEY": "secreto-fuerte-123456", "DB_PASSWORD": "clave-segura"}


def _settings(monkeypatch, **overrides):
    monkeypatch.delenv("OTP_HMAC_KEY", raising=False)
    return Settings(_env_file=None, **overrides)


def test_produccion_exige_otp_hmac_key(monkeypatch):
    with pytest.raises(ValueError, match="OTP_HMAC_KEY debe"):
        _settings(monkeypatch, **_BASE_PROD)


def test_produccion_rechaza_otp_hmac_key_corta(monkeypatch):
    with pytest.raises(ValueError, match="OTP_HMAC_KEY debe"):
        _settings(monkeypatch, **_BASE_PROD, OTP_HMAC_KEY="corta")


def test_produccion_rechaza_reutilizar_api_secret_key(monkeypatch):
    with pytest.raises(ValueError, match="distinta de API_SECRET_KEY"):
        _settings(monkeypatch, **_BASE_PROD, OTP_HMAC_KEY=_BASE_PROD["API_SECRET_KEY"])


def test_produccion_acepta_clave_dedicada(monkeypatch):
    settings = _settings(monkeypatch, **_BASE_PROD, OTP_HMAC_KEY="clave-otp-dedicada-0123456789")
    assert settings.OTP_HMAC_KEY == "clave-otp-dedicada-0123456789"


def test_desarrollo_genera_clave_si_falta(monkeypatch):
    settings = _settings(monkeypatch, APP_ENV="development", DEBUG=True)
    assert len(settings.OTP_HMAC_KEY) >= 16
    assert settings.OTP_HMAC_KEY != settings.API_SECRET_KEY
