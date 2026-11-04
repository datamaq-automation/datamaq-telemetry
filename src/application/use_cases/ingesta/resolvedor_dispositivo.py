"""src/application/use_cases/ingesta/resolvedor_dispositivo.py."""

import threading
import uuid
from datetime import datetime, timezone
from typing import Any, ClassVar

from src.domain.telemetria.entities import Dispositivo
from src.domain.telemetria.ports import (
    LoggerPort,
    RepositorioDispositivosPort,
    RepositorioOrganizacionesPort,
)
from src.domain.telemetria.value_objects import EstadoDispositivo, MacAddress


class ResolvedorDispositivoIngesta:
    """Gestiona la resolución, caché en memoria y ciclo de vida de dispositivos durante la ingesta."""

    _device_cache: ClassVar[dict[str, Dispositivo]] = {}
    _ultimos_heartbeats: ClassVar[dict[str, datetime]] = {}
    _organizacion_cache: ClassVar[dict[str, str | None]] = {}
    _lock: ClassVar[threading.Lock] = threading.Lock()

    @staticmethod
    def _clave_cache(mac_valor: str, medidor_id: int = 0) -> str:
        """Medidor 0 usa la MAC desnuda (compatibilidad con equipos de un medidor); el resto, MAC#n.

        Sin esto, los dos medidores de un Pro15 compartirían entrada de caché y se pisarían.
        """
        return mac_valor if medidor_id == 0 else f"{mac_valor}#{medidor_id}"

    @staticmethod
    def _consultar_uid(repo: RepositorioDispositivosPort, mac_vo: MacAddress, medidor_id: int) -> Dispositivo | None:
        """Lookup del medidor. Solo se pasa `medidor_id` cuando no es 0: el 0 es el default del puerto."""
        if medidor_id == 0:
            return repo.obtener_por_uid(mac_vo)
        return repo.obtener_por_uid(mac_vo, medidor_id)

    @staticmethod
    def _aplicar_dev_info(dispositivo: Dispositivo, dev_info: dict[str, Any] | None) -> None:
        if not dev_info:
            return
        if dev_info.get("serial_number"):
            dispositivo.numero_serie = dev_info.get("serial_number")
        if dev_info.get("device_fw"):
            dispositivo.version_fw = dev_info.get("device_fw")
        if dev_info.get("hw_model"):
            dispositivo.version_hw = dev_info.get("hw_model")

    @classmethod
    def _sincronizar_dispositivo_cacheado(
        cls,
        dispositivo: Dispositivo,
        mac_vo: MacAddress,
        dev_info: dict[str, Any] | None,
        ahora: datetime,
        repo_dispositivos: RepositorioDispositivosPort,
        medidor_id: int = 0,
    ) -> None:
        dispositivo_db = cls._consultar_uid(repo_dispositivos, mac_vo, medidor_id)
        if dispositivo_db:
            dispositivo.planta_id = dispositivo_db.planta_id
            dispositivo.tipo_instalacion = dispositivo_db.tipo_instalacion
            dispositivo.fases_con_ti = dispositivo_db.fases_con_ti
            dispositivo.ct_fases_invertidas = dispositivo_db.ct_fases_invertidas
            dispositivo.correccion_angular_fases = dispositivo_db.correccion_angular_fases
            # nuevos campos TI
            dispositivo.invertido = getattr(dispositivo_db, "invertido", False)
            dispositivo.orden_fases = getattr(dispositivo_db, "orden_fases", None)
            dispositivo.categoria_tarifaria = dispositivo_db.categoria_tarifaria
            dispositivo.penalizacion_reactiva_aplica = dispositivo_db.penalizacion_reactiva_aplica
            dispositivo.esta_activo = dispositivo_db.esta_activo

        dispositivo.marcar_online(ahora)
        cls._aplicar_dev_info(dispositivo, dev_info)
        repo_dispositivos.actualizar_heartbeat(
            dispositivo.id,
            dispositivo.estado,
            dispositivo.visto_por_ultima_vez or ahora,
            numero_serie=dispositivo.numero_serie,
            version_fw=dispositivo.version_fw,
            version_hw=dispositivo.version_hw,
        )
        cls._device_cache[cls._clave_cache(mac_vo.valor, medidor_id)] = dispositivo
        cls._ultimos_heartbeats[dispositivo.id] = ahora

    @classmethod
    def obtener_o_crear_dispositivo(
        cls,
        mac_raw: str,
        dev_info: dict[str, Any] | None,
        ahora: datetime | None,
        repo_dispositivos: RepositorioDispositivosPort,
        permitir_auto_registro: bool = True,
        logger: LoggerPort | None = None,
        medidor_id: int = 0,
    ) -> Dispositivo | None:
        mac_vo = MacAddress(mac_raw)
        if ahora is None:
            ahora = datetime.now(timezone.utc)
        clave = cls._clave_cache(mac_vo.valor, medidor_id)

        with cls._lock:
            # 1. Búsqueda en caché en memoria
            if clave in cls._device_cache:
                dispositivo = cls._device_cache[clave]
                ultimo_hb = cls._ultimos_heartbeats.get(dispositivo.id)

                if ultimo_hb is None or (ahora - ultimo_hb).total_seconds() >= 60:
                    cls._sincronizar_dispositivo_cacheado(
                        dispositivo, mac_vo, dev_info, ahora, repo_dispositivos, medidor_id
                    )

                return dispositivo

            # 2. Si no está en caché, consultar repositorio
            dispositivo = cls._consultar_uid(repo_dispositivos, mac_vo, medidor_id)
            if not dispositivo:
                if not permitir_auto_registro:
                    if logger:
                        logger.info(
                            "dispositivo_no_registrado_descartado", device_uid=mac_vo.valor, medidor_id=medidor_id
                        )
                    return None
                nuevo = Dispositivo(
                    id=str(uuid.uuid4()),
                    device_uid=mac_vo,
                    medidor_id=medidor_id,
                    nombre=f"Powermeter-{mac_vo.valor[-4:]}" + (f"-{medidor_id}" if medidor_id else ""),
                    modelo=dev_info.get("device_model", "SmartPlus") if dev_info else "SmartPlus",
                    numero_serie=dev_info.get("serial_number") if dev_info else None,
                    version_hw=dev_info.get("hw_model") if dev_info else None,
                    version_fw=dev_info.get("device_fw") if dev_info else None,
                    estado=EstadoDispositivo.ONLINE,
                    visto_por_ultima_vez=ahora,
                )
                saved = repo_dispositivos.guardar(nuevo)
                cls._device_cache[clave] = saved
                cls._ultimos_heartbeats[saved.id] = ahora
                if logger:
                    logger.info("nuevo_dispositivo_registrado", device_uid=mac_vo.valor, modelo=nuevo.modelo)
                return saved
            else:
                dispositivo.marcar_online(ahora)
                cls._aplicar_dev_info(dispositivo, dev_info)
                saved = repo_dispositivos.guardar(dispositivo)
                cls._device_cache[clave] = saved
                cls._ultimos_heartbeats[saved.id] = ahora
                return saved

    @classmethod
    def resolver_organizacion_id(
        cls,
        mac_raw: str,
        repo_organizaciones: RepositorioOrganizacionesPort,
    ) -> str | None:
        """Resuelve la organizacion_id de un dispositivo a partir de su MAC, vía device -> planta -> org.

        Usa la caché de dispositivos ya poblada por `obtener_o_crear_dispositivo` (no hace lookup
        de dispositivo por su cuenta) y cachea la resolución planta->org para evitar ir a la DB
        en cada mensaje. Devuelve None si el dispositivo no está en caché, no tiene planta asignada,
        o la planta no tiene organización.
        """
        mac_vo = MacAddress(mac_raw)
        # Resuelve el medidor 0 de la MAC. Un Pro15 con varios medidores necesita su propio medidor_id:
        # pendiente, no se decide acá implícitamente.
        dispositivo = cls._device_cache.get(cls._clave_cache(mac_vo.valor, 0))
        if dispositivo is None or not dispositivo.planta_id:
            return None

        planta_id = dispositivo.planta_id
        with cls._lock:
            if planta_id in cls._organizacion_cache:
                return cls._organizacion_cache[planta_id]

        planta = repo_organizaciones.obtener_planta_por_id(planta_id)
        organizacion_id = planta.organizacion_id if planta else None
        with cls._lock:
            cls._organizacion_cache[planta_id] = organizacion_id
        return organizacion_id

    @classmethod
    def invalidar_dispositivo(cls, mac_raw: str | MacAddress, medidor_id: int = 0) -> None:
        """Invalida la entrada de un medidor de la caché en memoria (por defecto, el medidor 0)."""
        mac_str = mac_raw.valor if isinstance(mac_raw, MacAddress) else str(mac_raw).upper()
        with cls._lock:
            cls._device_cache.pop(cls._clave_cache(mac_str, medidor_id), None)

    @classmethod
    def limpiar_cache(cls) -> None:
        """Limpia la caché de dispositivos en memoria (útil para pruebas)."""
        with cls._lock:
            cls._device_cache.clear()
            cls._ultimos_heartbeats.clear()
            cls._organizacion_cache.clear()
