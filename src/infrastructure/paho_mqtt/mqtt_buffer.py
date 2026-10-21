"""src/infrastructure/paho_mqtt/mqtt_buffer.py — Buffer resiliente en memoria para mensajes MQTT."""

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class MensajeBuffer:
    topic: str
    payload: dict | list
    intentos: int = 0
    proximo_reintento: float = 0.0
    timestamp_ingreso: float = field(default_factory=time.time)
    ultimo_error: str = ""


class BufferMensajesMQTT:
    """Buffer acotado en memoria para mensajes MQTT pendientes de persistencia ante fallos transitorios de BD (#60).

    Características:
    - Capacidad máxima acotada (max_size) para proteger la RAM.
    - Política de descarte FIFO (drop oldest) cuando se llena la capacidad, registrando el descarte.
    - Reintento con backoff exponencial.
    - Thread-safe mediante RLock.
    """

    def __init__(
        self,
        max_size: int = 1000,
        backoff_base_s: float = 2.0,
        backoff_max_s: float = 60.0,
        on_descarte: Callable[[MensajeBuffer], None] | None = None,
    ):
        self.max_size = max(1, max_size)
        self.backoff_base_s = backoff_base_s
        self.backoff_max_s = backoff_max_s
        self.on_descarte = on_descarte
        self._cola: deque[MensajeBuffer] = deque()
        self._lock = threading.RLock()
        self._descartados_total = 0

    @property
    def descartados_total(self) -> int:
        with self._lock:
            return self._descartados_total

    def __len__(self) -> int:
        with self._lock:
            return len(self._cola)

    def encolar(self, topic: str, payload: dict | list, error: str = "") -> None:
        """Agrega un mensaje al buffer de reintentos. Si está lleno, descarta el más antiguo (FIFO)."""
        with self._lock:
            if len(self._cola) >= self.max_size:
                descartado = self._cola.popleft()
                self._descartados_total += 1
                if self.on_descarte:
                    try:
                        self.on_descarte(descartado)
                    except Exception:
                        pass

            ahora = time.time()
            msg = MensajeBuffer(
                topic=topic,
                payload=payload,
                intentos=0,
                proximo_reintento=ahora + self.backoff_base_s,
                timestamp_ingreso=ahora,
                ultimo_error=error,
            )
            self._cola.append(msg)

    def procesar_pendientes(
        self,
        ejecutor: Callable[[str, dict | list], None],
        ignorar_backoff: bool = False,
    ) -> int:
        """Intenta reprocesar los mensajes encolados.

        Si `ignorar_backoff` es True (útil para pruebas unitarias deterministas), no espera
        a que se cumpla `proximo_reintento`.
        Si una llamada a `ejecutor` falla, aplica backoff exponencial a ese mensaje,
        lo reubica al final de la cola y detiene la ronda de reintentos para no saturar.
        """
        with self._lock:
            if not self._cola:
                return 0

            ahora = time.time()
            procesados_ok = 0
            n = len(self._cola)

            for _ in range(n):
                if not self._cola:
                    break
                msg = self._cola[0]
                if not ignorar_backoff and ahora < msg.proximo_reintento:
                    break

                self._cola.popleft()
                try:
                    ejecutor(msg.topic, msg.payload)
                    procesados_ok += 1
                except Exception as e:
                    msg.intentos += 1
                    msg.ultimo_error = str(e)
                    backoff = min(self.backoff_max_s, self.backoff_base_s * (2 ** (msg.intentos - 1)))
                    msg.proximo_reintento = time.time() + backoff
                    self._cola.append(msg)
                    break

            return procesados_ok

    def vaciar(self) -> None:
        with self._lock:
            self._cola.clear()
