"""src/infrastructure/paho_mqtt/metricas_deduplicacion.py — Métricas cuantitativas de deduplicación MQTT."""

import threading
from collections import defaultdict


class ContadorDuplicadosMqtt:
    """Contador acumulado thread-safe de mensajes duplicados descartados en ingesta MQTT."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._total: int = 0
        self._por_topico: dict[str, int] = defaultdict(int)

    def registrar(self, topico: str) -> None:
        """Registra el descarte de un mensaje duplicado para el tópico indicado."""
        with self._lock:
            self._total += 1
            self._por_topico[topico] += 1

    @property
    def total(self) -> int:
        """Total global de duplicados descartados."""
        with self._lock:
            return self._total

    def por_topico(self) -> dict[str, int]:
        """Copia del desglose de duplicados por tópico."""
        with self._lock:
            return dict(self._por_topico)

    def obtener(self, topico: str | None = None) -> int:
        """Retorna el conteo global si topico es None, o el conteo para el tópico dado."""
        with self._lock:
            if topico is not None:
                return self._por_topico.get(topico, 0)
            return self._total

    def limpiar(self) -> None:
        """Reinicia los contadores a cero."""
        with self._lock:
            self._total = 0
            self._por_topico.clear()
