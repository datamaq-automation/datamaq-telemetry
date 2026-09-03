import threading
import uuid
from datetime import datetime, timezone
from typing import Any, ClassVar

from src.domain.telemetria.entities import Dispositivo
from src.domain.telemetria.ports import LoggerPort, RepositorioDispositivosPort
from src.domain.telemetria.value_objects import EstadoDispositivo, MacAddress


class ResolvedorDispositivoIngesta:
    """Gestiona la resolución, caché en memoria y ciclo de vida de dispositivos durante la ingesta."""

    _device_cache: ClassVar[dict[str, Dispositivo]] = {}
    _ultimos_heartbeats: ClassVar[dict[str, datetime]] = {}
    _lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def obtener_o_crear_dispositivo(
        cls,
        mac_raw: str,
        dev_info: dict[str, Any] | None,
        ahora: datetime | None,
        repo_dispositivos: RepositorioDispositivosPort,
        permitir_auto_registro: bool = True,
        logger: LoggerPort | None = None,
    ) -> Dispositivo | None:
        mac_vo = MacAddress(mac_raw)
        if ahora is None:
            ahora = datetime.now(timezone.utc)

        with cls._lock:
            # 1. Búsqueda en caché en memoria
            if mac_vo.valor in cls._device_cache:
                dispositivo = cls._device_cache[mac_vo.valor]
                ultimo_hb = cls._ultimos_heartbeats.get(dispositivo.id)

                # Si venció la ventana de amortiguación (60s), persistir estado en DB
                if ultimo_hb is None or (ahora - ultimo_hb).total_seconds() >= 60:
                    dispositivo.marcar_online(ahora)
                    if dev_info:
                        if dev_info.get("serial_number"):
                            dispositivo.numero_serie = dev_info.get("serial_number")
                        if dev_info.get("device_fw"):
                            dispositivo.version_fw = dev_info.get("device_fw")
                        if dev_info.get("hw_model"):
                            dispositivo.version_hw = dev_info.get("hw_model")
                    dispositivo = repo_dispositivos.guardar(dispositivo)
                    cls._device_cache[mac_vo.valor] = dispositivo
                    cls._ultimos_heartbeats[dispositivo.id] = ahora

                return dispositivo

            # 2. Si no está en caché, consultar repositorio
            dispositivo = repo_dispositivos.obtener_por_uid(mac_vo)
            if not dispositivo:
                if not permitir_auto_registro:
                    if logger:
                        logger.info("dispositivo_no_registrado_descartado", device_uid=mac_vo.valor)
                    return None
                nuevo = Dispositivo(
                    id=str(uuid.uuid4()),
                    device_uid=mac_vo,
                    nombre=f"Powermeter-{mac_vo.valor[-4:]}",
                    modelo=dev_info.get("device_model", "SmartPlus") if dev_info else "SmartPlus",
                    numero_serie=dev_info.get("serial_number") if dev_info else None,
                    version_hw=dev_info.get("hw_model") if dev_info else None,
                    version_fw=dev_info.get("device_fw") if dev_info else None,
                    estado=EstadoDispositivo.ONLINE,
                    visto_por_ultima_vez=ahora,
                )
                saved = repo_dispositivos.guardar(nuevo)
                cls._device_cache[mac_vo.valor] = saved
                cls._ultimos_heartbeats[saved.id] = ahora
                if logger:
                    logger.info("nuevo_dispositivo_registrado", device_uid=mac_vo.valor, modelo=nuevo.modelo)
                return saved
            else:
                dispositivo.marcar_online(ahora)
                if dev_info:
                    if dev_info.get("serial_number"):
                        dispositivo.numero_serie = dev_info.get("serial_number")
                    if dev_info.get("device_fw"):
                        dispositivo.version_fw = dev_info.get("device_fw")
                    if dev_info.get("hw_model"):
                        dispositivo.version_hw = dev_info.get("hw_model")
                saved = repo_dispositivos.guardar(dispositivo)
                cls._device_cache[mac_vo.valor] = saved
                cls._ultimos_heartbeats[saved.id] = ahora
                return saved

    @classmethod
    def limpiar_cache(cls) -> None:
        """Limpia la caché de dispositivos en memoria (útil para pruebas)."""
        with cls._lock:
            cls._device_cache.clear()
            cls._ultimos_heartbeats.clear()
