"""tests/unit/test_otp_hmac_key_config.py — Clave dedicada para firmar los OTP de cambio de contraseña.

En producción, una clave ausente, corta o igual a API_SECRET_KEY NO aborta el arranque: la API levanta,
loguea un error crítico y los endpoints de cambio de contraseña responden 503 hasta cargarla.
"""

import logging

import pytest

from src.infrastructure.settings.config import Settings

# APP_ENV y DEBUG explícitos: el entorno del proceso (CI exporta APP_ENV=test) no debe decidir la postura.
_PERFIL_PROD = {"APP_ENV": "production", "DEBUG": False}
_BASE_PROD = {**_PERFIL_PROD, "API_SECRET_KEY": "secreto-fuerte-123456", "DB_PASSWORD": "clave-segura"}


def _settings(monkeypatch, **overrides):
    monkeypatch.delenv("OTP_HMAC_KEY", raising=False)
    return Settings(_env_file=None, **overrides)


def test_produccion_sin_otp_arranca_y_marca_no_configurada(monkeypatch, caplog):
    with caplog.at_level(logging.CRITICAL):
        settings = _settings(monkeypatch, **_BASE_PROD)
    assert settings.otp_hmac_configurada is False
    assert any(r.levelno == logging.CRITICAL and "OTP_HMAC_KEY" in r.getMessage() for r in caplog.records)


def test_produccion_con_otp_corta_arranca_y_marca_no_configurada(monkeypatch, caplog):
    with caplog.at_level(logging.CRITICAL):
        settings = _settings(monkeypatch, **_BASE_PROD, OTP_HMAC_KEY="corta")
    assert settings.otp_hmac_configurada is False
    assert any(r.levelno == logging.CRITICAL for r in caplog.records)


def test_produccion_con_otp_igual_a_api_secret_arranca_y_marca_no_configurada(monkeypatch):
    settings = _settings(monkeypatch, **_BASE_PROD, OTP_HMAC_KEY=_BASE_PROD["API_SECRET_KEY"])
    assert settings.otp_hmac_configurada is False


def test_produccion_acepta_clave_dedicada(monkeypatch, caplog):
    with caplog.at_level(logging.CRITICAL):
        settings = _settings(monkeypatch, **_BASE_PROD, OTP_HMAC_KEY="clave-otp-dedicada-0123456789")
    assert settings.OTP_HMAC_KEY == "clave-otp-dedicada-0123456789"
    assert settings.otp_hmac_configurada is True
    assert not caplog.records


def test_desarrollo_genera_clave_si_falta(monkeypatch):
    settings = _settings(monkeypatch, APP_ENV="development", DEBUG=True)
    assert len(settings.OTP_HMAC_KEY) >= 16
    assert settings.OTP_HMAC_KEY != settings.API_SECRET_KEY
    assert settings.otp_hmac_configurada is True


def test_produccion_sigue_abortando_por_otros_secretos(monkeypatch):
    # El aborto de arranque se mantiene para el resto de los secretos.
    with pytest.raises(ValueError, match="DB_PASSWORD"):
        _settings(
            monkeypatch,
            **_PERFIL_PROD,
            API_SECRET_KEY="secreto-fuerte-123456",
            OTP_HMAC_KEY="clave-otp-dedicada-0123456789",
        )
