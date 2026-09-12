"""src/adapters/gateways/in_memory_event_broadcaster.py."""
from collections.abc import Callable
from typing import Any

from src.domain.telemetria.ports import PublicadorEventosPort


class InMemoryEventBroadcaster(PublicadorEventosPort):
    def __init__(self):
        self._listeners: list[Callable[[str, dict[str, Any]], None]] = []

    def suscribir(self, listener: Callable[[str, dict[str, Any]], None]) -> None:
        self._listeners.append(listener)

    def desuscribir(self, listener: Callable[[str, dict[str, Any]], None]) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def publicar_telemetria_en_vivo(self, topico: str, datos: dict[str, Any]) -> None:
        for listener in list(self._listeners):
            try:
                listener(topico, datos)
            except Exception:
                pass
