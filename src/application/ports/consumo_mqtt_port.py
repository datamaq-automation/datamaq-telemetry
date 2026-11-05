"""src/application/ports/consumo_mqtt_port.py — Contrato de lectura del consumo MQTT por hora (#93)."""

from datetime import datetime
from typing import Protocol


class RepositorioConsumoMqttPort(Protocol):
    """Lectura de solo lectura: filas (hora, mensajes, bytes_payload) del equipo en [desde, hasta)."""

    def consultar(self, uid: str, desde: datetime, hasta: datetime) -> list[tuple[datetime, int, int]]: ...
