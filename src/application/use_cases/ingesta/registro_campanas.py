"""src/application/use_cases/ingesta/registro_campanas.py — Registro en memoria de las campañas activas por dispositivo."""

import threading
from datetime import datetime, timezone


class RegistroCampanasActivas:
    """Qué dispositivos están capturando a alta resolución en este instante.

    Vive en memoria y no en la base porque se consulta **una vez por cada lectura MQTT
    entrante** — a caudal de ráfaga, varias por segundo y por dispositivo. Un SELECT
    por lectura pondría la base en el camino crítico de la ingesta para responder, casi
    siempre, que no hay ninguna campaña.

    **Depende de que la API y el listener MQTT compartan proceso** (el listener corre
    dentro del lifespan de FastAPI, `server.py`) y de que se ejecute un solo worker de
    uvicorn (`systemd/datamaq-api.service`). Si alguna de esas dos cosas cambia, este
    registro deja de ver las campañas que abre la API y hay que moverlo a la base o a
    un almacén compartido.

    La fuente de verdad sigue siendo la tabla: el registro se rehidrata al arrancar
    desde las campañas `EN_CURSO`, así que perderlo por un reinicio no pierde datos.
    """

    def __init__(self) -> None:
        self._activas: dict[str, tuple[str, datetime]] = {}
        self._lock = threading.Lock()

    def activar(self, dispositivo_id: str, campana_id: str, fin_planificado_at: datetime) -> None:
        with self._lock:
            self._activas[dispositivo_id] = (campana_id, fin_planificado_at)

    def desactivar(self, dispositivo_id: str) -> None:
        with self._lock:
            self._activas.pop(dispositivo_id, None)

    def campana_de(self, dispositivo_id: str, ahora: datetime | None = None) -> str | None:
        """Id de la campaña vigente, o `None`.

        Una campaña vencida se descarta acá mismo aunque nadie la haya cerrado todavía:
        el cierre ordenado lo hace el bucle del servidor, pero mientras tanto no debe
        seguir capturando.
        """
        momento = ahora or datetime.now(timezone.utc)
        with self._lock:
            entrada = self._activas.get(dispositivo_id)
            if entrada is None:
                return None
            campana_id, fin = entrada
            if momento >= fin:
                self._activas.pop(dispositivo_id, None)
                return None
            return campana_id

    def dispositivos_activos(self) -> list[str]:
        with self._lock:
            return list(self._activas.keys())

    def limpiar(self) -> None:
        with self._lock:
            self._activas.clear()


registro_campanas_activas = RegistroCampanasActivas()
"""Singleton de proceso, compartido entre la API que abre campañas y la ingesta que captura."""
