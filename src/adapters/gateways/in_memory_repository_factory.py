"""src/adapters/gateways/in_memory_repository_factory.py.

Implementación en memoria de RepositorioFactoryPort para testing y ejecución desacoplada.
"""

from __future__ import annotations

from src.domain.telemetria.ports import (
    RepositorioDispositivosPort,
    RepositorioFactoryPort,
    RepositorioPlanesPort,
    RepositorioSuscripcionesPort,
    RepositorioTelemetriaPort,
)


class InMemoryRepositorioFactory(RepositorioFactoryPort):
    """Abstract Factory en memoria que provee o inyecta repositorios para testing y mocks."""

    def __init__(
        self,
        dispositivos: RepositorioDispositivosPort | None = None,
        telemetria: RepositorioTelemetriaPort | None = None,
        suscripciones: RepositorioSuscripcionesPort | None = None,
        planes: RepositorioPlanesPort | None = None,
    ) -> None:
        self._dispositivos = dispositivos
        self._telemetria = telemetria
        self._suscripciones = suscripciones
        self._planes = planes

    def dispositivos(self) -> RepositorioDispositivosPort:
        if self._dispositivos is None:
            raise NotImplementedError("Repositorio de dispositivos no configurado en InMemoryRepositorioFactory")
        return self._dispositivos

    def telemetria(self) -> RepositorioTelemetriaPort:
        if self._telemetria is None:
            raise NotImplementedError("Repositorio de telemetría no configurado en InMemoryRepositorioFactory")
        return self._telemetria

    def suscripciones(self) -> RepositorioSuscripcionesPort:
        if self._suscripciones is None:
            raise NotImplementedError("Repositorio de suscripciones no configurado en InMemoryRepositorioFactory")
        return self._suscripciones

    def planes(self) -> RepositorioPlanesPort:
        if self._planes is None:
            raise NotImplementedError("Repositorio de planes no configurado en InMemoryRepositorioFactory")
        return self._planes
