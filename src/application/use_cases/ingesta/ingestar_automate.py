"""src/application/use_cases/ingesta/ingestar_automate.py."""
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, ClassVar

from src.application.use_cases.gestionar_disponibilidad import GestionarDisponibilidadUseCase
from src.domain.disponibilidad.value_objects import EstadoMaquina
from src.domain.telemetria.entities import Dispositivo
from src.domain.telemetria.ports import LoggerPort, RepositorioDispositivosPort
from src.domain.telemetria.value_objects import EstadoDispositivo, MacAddress


class CalculadorCadenciaProduccionService:
    """Calcula impulsos por minuto (PPM) en ventana deslizante de 60 segundos."""

    def __init__(self, umbral_marcha_ppm: float = 30.0, ventana_segundos: int = 60):
        self.umbral_marcha_ppm = umbral_marcha_ppm
        self.ventana_segundos = ventana_segundos
        self._historial_impulsos: dict[str, list[datetime]] = {}
        self._lock = threading.Lock()

    def registrar_impulso(self, device_id: str, timestamp: datetime | None = None) -> float:
        ts = timestamp or datetime.now(timezone.utc)
        limite = ts - timedelta(seconds=self.ventana_segundos)

        with self._lock:
            if device_id not in self._historial_impulsos:
                self._historial_impulsos[device_id] = []

            # Filtrar impulsos viejos fuera de la ventana
            recientes = [t for t in self._historial_impulsos[device_id] if t >= limite]
            recientes.append(ts)
            self._historial_impulsos[device_id] = recientes

            # Frecuencia en la ventana
            count = len(recientes)
            return float(count)

    def determinar_estado(self, ppm: float) -> str:
        if ppm >= self.umbral_marcha_ppm:
            return EstadoMaquina.MARCHA.value
        return EstadoMaquina.PARADA.value


class IngestarAutomateUseCase:
    _device_cache: ClassVar[dict[str, Dispositivo]] = {}
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(
        self,
        repo_dispositivos: RepositorioDispositivosPort,
        disponibilidad_use_case: GestionarDisponibilidadUseCase | None = None,
        logger: LoggerPort | None = None,
        permitir_auto_registro: bool = True,
        calculador_cadencia: CalculadorCadenciaProduccionService | None = None,
    ):
        self.repo_dispositivos = repo_dispositivos
        self.disponibilidad_use_case = disponibilidad_use_case
        self.logger = logger
        self.permitir_auto_registro = permitir_auto_registro
        self.calculador_cadencia = calculador_cadencia or CalculadorCadenciaProduccionService()

    def _obtener_o_crear_dispositivo(self, device_uid_raw: str, ahora: datetime) -> Dispositivo | None:
        uid_limpio = device_uid_raw.replace(":", "").replace("-", "").upper()

        # Ajuste a 12 caracteres hex para MacAddress si es más corto o formato custom
        if len(uid_limpio) < 12:
            uid_limpio = uid_limpio.zfill(12)
        elif len(uid_limpio) > 12:
            uid_limpio = uid_limpio[-12:]

        try:
            mac_vo = MacAddress(uid_limpio)
        except Exception:
            return None

        with self._lock:
            if mac_vo.valor in self._device_cache:
                disp = self._device_cache[mac_vo.valor]
                disp.marcar_online(ahora)
                return disp

            disp = self.repo_dispositivos.obtener_por_uid(mac_vo)
            if not disp:
                if not self.permitir_auto_registro:
                    return None
                nuevo = Dispositivo(
                    id=str(uuid.uuid4()),
                    device_uid=mac_vo,
                    nombre=f"Automate-{mac_vo.valor[-4:]}",
                    modelo="Automate24V4M",
                    estado=EstadoDispositivo.ONLINE,
                    visto_por_ultima_vez=ahora,
                )
                saved = self.repo_dispositivos.guardar(nuevo)
                self._device_cache[mac_vo.valor] = saved
                return saved
            else:
                disp.marcar_online(ahora)
                saved = self.repo_dispositivos.guardar(disp)
                self._device_cache[mac_vo.valor] = saved
                return saved

    def ejecutar(self, topico: str, payload: Any) -> None:
        partes = topico.split("/")
        if len(partes) < 3:
            return

        device_uid_raw = partes[1]
        subtopico = partes[2] if len(partes) > 2 else ""
        subtopico_secundario = partes[3] if len(partes) > 3 else ""

        ahora = datetime.now(timezone.utc)
        dispositivo = self._obtener_o_crear_dispositivo(device_uid_raw, ahora)
        if not dispositivo:
            return

        self.repo_dispositivos.actualizar_heartbeat(
            dispositivo.id,
            dispositivo.estado,
            ahora,
        )

        # Ingesta de E/S discretas y analógicas
        if subtopico == "inst" and subtopico_secundario == "io":
            items = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else []
            for item in items:
                if not isinstance(item, dict):
                    continue
                puerto_id = item.get("id")
                valor = item.get("v")

                # Conteo de impulsos en puerto de producción (ej: puerto 1)
                if puerto_id == 1 and valor in (1, 1.0, True):
                    ppm = self.calculador_cadencia.registrar_impulso(dispositivo.id, ahora)
                    nuevo_estado = self.calculador_cadencia.determinar_estado(ppm)

                    if self.disponibilidad_use_case:
                        # Evaluar disponibilidad por cadence de producción
                        self._actualizar_disponibilidad_por_ppm(dispositivo.id, nuevo_estado, ppm, ahora)

    def _actualizar_disponibilidad_por_ppm(
        self, dispositivo_id: str, nuevo_estado: str, ppm: float, ahora: datetime
    ) -> None:
        if not self.disponibilidad_use_case:
            return
        try:
            potencia_simulada = ppm * 10.0 if nuevo_estado == "MARCHA" else 0.0
            self.disponibilidad_use_case.clasificar_lectura(
                dispositivo_id=dispositivo_id,
                potencia_w=potencia_simulada,
                recorded_at=ahora,
            )
        except Exception as e:
            if self.logger:
                self.logger.error("error_actualizar_disponibilidad_ppm", error=str(e))
