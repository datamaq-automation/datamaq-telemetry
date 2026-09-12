"""src/adapters/gateways/in_memory_telemetria_buffer.py."""
import threading
from collections import deque

from src.domain.telemetria.ports import BufferTelemetriaEnVivoPort


class InMemoryTelemetriaBuffer(BufferTelemetriaEnVivoPort):
    """Buffer en RAM de las últimas lecturas `inst` por dispositivo, alimentado como
    suscriptor del mismo broadcaster que difunde por WebSocket. Sirve para que la
    respuesta REST de históricos incluya lecturas recientes que todavía no bajaron a
    la base de datos (downsampling de persistencia), sin depender del navegador."""

    def __init__(self, max_por_dispositivo: int = 120):
        self._buffers: dict[str, deque[dict]] = {}
        self._max_por_dispositivo = max_por_dispositivo
        self._lock = threading.Lock()

    def agregar(self, topico: str, datos: dict) -> None:
        if not topico.endswith("/inst"):
            return
        dispositivo_id = datos.get("dispositivo_id")
        if not dispositivo_id:
            return
        with self._lock:
            buffer = self._buffers.setdefault(dispositivo_id, deque(maxlen=self._max_por_dispositivo))
            buffer.append(datos)

    def obtener(self, dispositivo_id: str) -> list[dict]:
        with self._lock:
            buffer = self._buffers.get(dispositivo_id)
            return list(buffer) if buffer else []
