"""Emails del cambio de contraseña: el código va en el cuerpo, nunca en logs ni se filtra la contraseña."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.infrastructure.auth import email_service as modulo
from src.infrastructure.auth.email_service import SmtpEmailService


@pytest.fixture()
def capturar_smtp(monkeypatch):
    capturados: list[tuple[object, str, str]] = []

    def fake_enviar(self, msg, log_event, destinatario):
        capturados.append((msg, log_event, destinatario))
        return True

    monkeypatch.setattr(SmtpEmailService, "_enviar_smtp", fake_enviar)
    return capturados


def test_codigo_viaja_en_el_cuerpo_y_el_asunto_es_el_de_la_decision(capturar_smtp):
    svc = SmtpEmailService(app_env="production")

    assert svc.enviar_codigo_cambio_contrasena("usuario@example.com", "0427") is True

    msg, evento, destino = capturar_smtp[0]
    assert msg["Subject"] == "Confirmación: Cambiar Contraseña en DataMaq"
    assert "0427" in msg.get_content()
    assert evento == "email_cambio_contrasena_codigo"
    assert destino == "usuario@example.com"


def test_modo_test_no_loguea_el_codigo(monkeypatch):
    logger_mock = MagicMock()
    monkeypatch.setattr(modulo, "logger", logger_mock)
    svc = SmtpEmailService(app_env="test")

    svc.enviar_codigo_cambio_contrasena("usuario@example.com", "0427")

    assert "0427" not in str(logger_mock.mock_calls)
    logger_mock.info.assert_called_once()


def test_confirmacion_incluye_momento_e_ip_y_no_codigo_ni_contrasena(capturar_smtp):
    svc = SmtpEmailService(app_env="production")
    momento = datetime(2026, 10, 8, 12, 30, tzinfo=timezone.utc)

    assert svc.notificar_cambio_contrasena("usuario@example.com", momento, "10.0.0.7") is True

    msg, evento, _ = capturar_smtp[0]
    cuerpo = msg.get_content()
    assert momento.isoformat() in cuerpo
    assert "10.0.0.7" in cuerpo
    assert evento == "email_cambio_contrasena_confirmado"
    assert "contraseña:" not in cuerpo.lower()


def test_confirmacion_sin_ip_no_rompe(capturar_smtp):
    svc = SmtpEmailService(app_env="production")
    svc.notificar_cambio_contrasena("usuario@example.com", datetime.now(timezone.utc), None)
    assert "desconocida" in capturar_smtp[0][0].get_content()
