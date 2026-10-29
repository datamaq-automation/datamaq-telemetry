"""src/domain/telemetria/servicios/consumo_mqtt.py — Agregado de mensajes y bytes de payload por dispositivo y hora (#93).

Mide lo que llega al servidor, no el consumo del chip: el consumo real lo mide el operador.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime


def normalizar_uid(uid: str) -> str:
    """UID en hex mayúsculas sin separadores: la forma en que el tópico ``m/wifi/{UID}/...`` lo trae."""
    return uid.replace(":", "").replace("-", "").upper()


def uid_desde_topico(topico: str) -> str | None:
    """UID normalizado del tópico ``m/wifi/{UID}/...``, o None si el tópico no tiene esa forma."""
    partes = topico.split("/")
    if len(partes) < 4 or partes[0] != "m" or partes[1] != "wifi":
        return None
    return normalizar_uid(partes[2]) or None


def hora_inicio(momento: datetime) -> datetime:
    """Inicio de la hora (UTC) a la que pertenece el instante."""
    return momento.replace(minute=0, second=0, microsecond=0)


@dataclass
class ContadorConsumo:
    mensajes: int = 0
    bytes_payload: int = 0


class AcumuladorConsumoHorario:
    """Suma mensajes y bytes por (UID, hora). Thread-safe; ``extraer`` vacía el acumulado."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._datos: dict[tuple[str, datetime], ContadorConsumo] = {}

    def registrar(self, uid: str, tamano_bytes: int, momento: datetime) -> None:
        clave = (uid, hora_inicio(momento))
        with self._lock:
            contador = self._datos.get(clave)
            if contador is None:
                contador = self._datos[clave] = ContadorConsumo()
            contador.mensajes += 1
            contador.bytes_payload += tamano_bytes

    def extraer(self) -> dict[tuple[str, datetime], ContadorConsumo]:
        """Devuelve lo acumulado y reinicia el acumulador."""
        with self._lock:
            datos, self._datos = self._datos, {}
        return datos

    def fusionar(self, datos: dict[tuple[str, datetime], ContadorConsumo]) -> None:
        """Devuelve al acumulado lo que no se pudo persistir, para no perder mensajes ante un fallo de base."""
        with self._lock:
            for clave, contador in datos.items():
                propio = self._datos.get(clave)
                if propio is None:
                    self._datos[clave] = contador
                else:
                    propio.mensajes += contador.mensajes
                    propio.bytes_payload += contador.bytes_payload
