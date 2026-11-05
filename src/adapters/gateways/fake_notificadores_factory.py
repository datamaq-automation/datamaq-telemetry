"""src/adapters/gateways/fake_notificadores_factory.py.

Abstract Factory en memoria para la familia de emisión de alertas y eventos.
"""

from __future__ import annotations

from src.domain.telemetria.ports import (
    NotificadorAlertasPort,
    NotificadoresFactoryPort,
    PublicadorEventosPort,
)


class FakeNotificadoresFactory(NotificadoresFactoryPort):
    """Abstract Factory desacoplada para testing hermético de flujos de notificación."""

    def __init__(
        self,
        notificador: NotificadorAlertasPort | None = None,
        publicador: PublicadorEventosPort | None = None,
    ) -> None:
        self._notificador = notificador
        self._publicador = publicador

    def notificador_alertas(self) -> NotificadorAlertasPort:
        if self._notificador is None:
            raise NotImplementedError("Notificador de alertas no configurado en FakeNotificadoresFactory")
        return self._notificador

    def publicador_eventos(self) -> PublicadorEventosPort:
        if self._publicador is None:
            raise NotImplementedError("Publicador de eventos no configurado en FakeNotificadoresFactory")
        return self._publicador
