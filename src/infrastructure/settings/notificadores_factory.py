"""src/infrastructure/settings/notificadores_factory.py.

Implementación concreta de NotificadoresFactoryPort para producción.
"""

from __future__ import annotations

from src.adapters.gateways.in_memory_event_broadcaster import InMemoryEventBroadcaster
from src.domain.telemetria.ports import (
    NotificadorAlertasPort,
    NotificadoresFactoryPort,
    PublicadorEventosPort,
)
from src.infrastructure.auth.email_service import SmtpEmailService
from src.infrastructure.settings.config import Settings


class ProduccionNotificadoresFactory(NotificadoresFactoryPort):
    """Abstract Factory que resuelve la suite operativa de notificación y eventos."""

    def __init__(self, settings: Settings, broadcaster: PublicadorEventosPort | None = None) -> None:
        self._settings = settings
        self._broadcaster = broadcaster

    def notificador_alertas(self) -> NotificadorAlertasPort:
        return SmtpEmailService(
            host=self._settings.SMTP_HOST,
            port=self._settings.SMTP_PORT,
            user=self._settings.SMTP_USER,
            password=self._settings.SMTP_PASSWORD,
            use_tls=self._settings.SMTP_TLS,
            from_email=self._settings.SMTP_FROM,
            app_env=self._settings.APP_ENV,
        )

    def publicador_eventos(self) -> PublicadorEventosPort:
        return self._broadcaster or InMemoryEventBroadcaster()
