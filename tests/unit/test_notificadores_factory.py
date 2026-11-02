"""tests/unit/test_notificadores_factory.py — Tests para Abstract Factory de Notificaciones."""

from unittest.mock import MagicMock

import pytest

from src.adapters.gateways.fake_notificadores_factory import FakeNotificadoresFactory
from src.domain.telemetria.ports import (
    NotificadorAlertasPort,
    NotificadoresFactoryPort,
    PublicadorEventosPort,
)
from src.infrastructure.settings.config import Settings
from src.infrastructure.settings.notificadores_factory import ProduccionNotificadoresFactory


class TestProduccionNotificadoresFactory:
    def test_implementa_interfaz_notificadores_factory_port(self):
        settings = Settings(
            DATABASE_URL="sqlite:///:memory:",
            JWT_SECRET_KEY="test_secret",
            ALERTAS_EMAIL_DESTINATARIOS="admin@example.com",
            SMTP_HOST="smtp.example.com",
            SMTP_PORT=587,
            SMTP_USER="user",
            SMTP_PASSWORD="password",
            SMTP_FROM="noreply@example.com",
            SMTP_TLS=True,
            APP_ENV="test",
        )
        factory = ProduccionNotificadoresFactory(settings)
        assert isinstance(factory, NotificadoresFactoryPort)

    def test_crea_notificador_alertas_y_publicador(self):
        settings = Settings(
            DATABASE_URL="sqlite:///:memory:",
            JWT_SECRET_KEY="test_secret",
            ALERTAS_EMAIL_DESTINATARIOS="admin@example.com",
            SMTP_HOST="smtp.example.com",
            SMTP_PORT=587,
            SMTP_USER="user",
            SMTP_PASSWORD="password",
            SMTP_FROM="noreply@example.com",
            SMTP_TLS=True,
            APP_ENV="test",
        )
        mock_broadcaster = MagicMock(spec=PublicadorEventosPort)
        factory = ProduccionNotificadoresFactory(settings, broadcaster=mock_broadcaster)

        notificador = factory.notificador_alertas()
        assert isinstance(notificador, NotificadorAlertasPort)

        publicador = factory.publicador_eventos()
        assert publicador is mock_broadcaster


class TestFakeNotificadoresFactory:
    def test_implementa_interfaz_notificadores_factory_port(self):
        factory = FakeNotificadoresFactory()
        assert isinstance(factory, NotificadoresFactoryPort)

    def test_provee_notificadores_inyectados(self):
        mock_notif = MagicMock(spec=NotificadorAlertasPort)
        mock_pub = MagicMock(spec=PublicadorEventosPort)
        factory = FakeNotificadoresFactory(notificador=mock_notif, publicador=mock_pub)

        assert factory.notificador_alertas() is mock_notif
        assert factory.publicador_eventos() is mock_pub

    def test_lanza_error_cuando_no_esta_configurado(self):
        factory = FakeNotificadoresFactory()
        with pytest.raises(NotImplementedError):
            factory.notificador_alertas()
        with pytest.raises(NotImplementedError):
            factory.publicador_eventos()
