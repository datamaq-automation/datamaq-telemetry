import threading
from datetime import datetime, timezone


class CooldownNotificacionesAlertasService:
    """Gestiona el período de gracia (cooldown/debounce) para notificaciones de alertas.

    Garantiza que no se emita más de un correo para la misma alerta en el mismo dispositivo
    dentro del lapso configurado (por defecto 1800 segundos = 30 minutos).
    """

    def __init__(self, cooldown_segundos: float = 1800.0) -> None:
        self.cooldown_segundos = cooldown_segundos
        self._ultimas_notificaciones: dict[tuple[str, str], datetime] = {}
        self._lock = threading.Lock()

    def _clave(self, dispositivo_id: str, tipo_alerta: str) -> tuple[str, str]:
        return (dispositivo_id, tipo_alerta)

    def debe_notificar(
        self,
        dispositivo_id: str,
        tipo_alerta: str,
        ahora: datetime | None = None,
    ) -> bool:
        """Determina si la alerta califica para envío según el cooldown transcurrido."""
        momento = ahora or datetime.now(timezone.utc)
        clave = self._clave(dispositivo_id, tipo_alerta)
        with self._lock:
            ultima = self._ultimas_notificaciones.get(clave)
            if ultima is None:
                return True
            transcurrido = (momento - ultima).total_seconds()
            return transcurrido >= self.cooldown_segundos

    def registrar_notificacion(
        self,
        dispositivo_id: str,
        tipo_alerta: str,
        ahora: datetime | None = None,
    ) -> None:
        """Registra el instante de la notificación despachada."""
        momento = ahora or datetime.now(timezone.utc)
        clave = self._clave(dispositivo_id, tipo_alerta)
        with self._lock:
            self._ultimas_notificaciones[clave] = momento

    def resetear(self, dispositivo_id: str, tipo_alerta: str) -> None:
        """Remueve la entrada para permitir notificación inmediata tras normalización."""
        clave = self._clave(dispositivo_id, tipo_alerta)
        with self._lock:
            self._ultimas_notificaciones.pop(clave, None)

    def limpiar(self) -> None:
        """Limpia todo el estado en memoria."""
        with self._lock:
            self._ultimas_notificaciones.clear()
