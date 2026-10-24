"""tests/unit/test_mp_webhook_secret_config.py — Secreto del webhook de Mercado Pago (Issue #45).

Con billing activo y MP_WEBHOOK_SECRET vacío, cualquiera podría firmar con clave vacía. El arranque NO aborta
(producción puede tener billing encendido sin el secreto cargado): se loguea CRITICAL y el webhook responde 503.
"""

import logging

from src.infrastructure.settings.config import Settings


def _settings(monkeypatch, **overrides):
    monkeypatch.delenv("MP_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("BILLING_HABILITADO", raising=False)
    return Settings(_env_file=None, **overrides)


def test_secreto_vacio_no_es_configurado(monkeypatch):
    settings = _settings(monkeypatch, APP_ENV="development", DEBUG=True, MP_WEBHOOK_SECRET="")
    assert settings.mp_webhook_secret_configurado is False


def test_secreto_solo_espacios_no_es_configurado(monkeypatch):
    settings = _settings(monkeypatch, APP_ENV="development", DEBUG=True, MP_WEBHOOK_SECRET="   ")
    assert settings.mp_webhook_secret_configurado is False


def test_secreto_presente_es_configurado(monkeypatch):
    settings = _settings(monkeypatch, APP_ENV="development", DEBUG=True, MP_WEBHOOK_SECRET="secreto-mp-123")
    assert settings.mp_webhook_secret_configurado is True


def test_produccion_billing_activo_sin_secreto_arranca_y_loguea_critical(monkeypatch, caplog):
    with caplog.at_level(logging.CRITICAL):
        settings = _settings(
            monkeypatch,
            APP_ENV="production",
            DEBUG=False,
            API_SECRET_KEY="secreto-fuerte-123456",
            DB_PASSWORD="clave-segura",
            OTP_HMAC_KEY="clave-otp-dedicada-0123456789",
            BILLING_HABILITADO=True,
            MP_WEBHOOK_SECRET="",
        )
    assert settings.mp_webhook_secret_configurado is False
    assert any(r.levelno == logging.CRITICAL and "MP_WEBHOOK_SECRET" in r.getMessage() for r in caplog.records)


def test_produccion_billing_deshabilitado_sin_secreto_no_loguea_critical(monkeypatch, caplog):
    with caplog.at_level(logging.CRITICAL):
        _settings(
            monkeypatch,
            APP_ENV="production",
            DEBUG=False,
            API_SECRET_KEY="secreto-fuerte-123456",
            DB_PASSWORD="clave-segura",
            OTP_HMAC_KEY="clave-otp-dedicada-0123456789",
            BILLING_HABILITADO=False,
            MP_WEBHOOK_SECRET="",
        )
    assert not any("MP_WEBHOOK_SECRET" in r.getMessage() for r in caplog.records)
