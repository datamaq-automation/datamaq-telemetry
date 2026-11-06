"""src/adapters/gateways/in_memory_event_broadcaster.py."""

import logging
from collections.abc import Callable
from typing import Any

from src.domain.telemetria.ports import LoggerPort, PublicadorEventosPort

_log = logging.getLogger("broadcaster")


class _LoggerStdlib(LoggerPort):
    """Logger por defecto: stdlib, para que el adaptador no dependa de infraestructura (datamaq#149)."""

    def debug(self, evento: str, **kwargs: object) -> None:
        _log.debug("%s %s", evento, kwargs)

    def info(self, evento: str, **kwargs: object) -> None:
        _log.info("%s %s", evento, kwargs)

    def warning(self, evento: str, **kwargs: object) -> None:
        _log.warning("%s %s", evento, kwargs)

    def error(self, evento: str, **kwargs: object) -> None:
        _log.error("%s %s", evento, kwargs)


def _nombre_del_listener(listener: Callable[..., Any]) -> str:
    return getattr(listener, "__qualname__", None) or repr(listener)


class InMemoryEventBroadcaster(PublicadorEventosPort):
    def __init__(self, logger: LoggerPort | None = None) -> None:
        self._listeners: list[Callable[[str, dict[str, Any]], None]] = []
        self._logger: LoggerPort = logger or _LoggerStdlib()

    def suscribir(self, listener: Callable[[str, dict[str, Any]], None]) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def desuscribir(self, listener: Callable[[str, dict[str, Any]], None]) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def publicar_telemetria_en_vivo(self, topico: str, datos: dict[str, Any]) -> None:
        for listener in list(self._listeners):
            try:
                listener(topico, datos)
            except Exception as exc:
                # Un listener roto no debe cortar a los demás, pero su fallo queda registrado (datamaq#149).
                self._logger.error(
                    "listener_broadcast_fallo",
                    topico=topico,
                    listener=_nombre_del_listener(listener),
                    tipo=type(exc).__name__,
                    error=str(exc),
                )
