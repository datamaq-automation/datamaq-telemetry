"""src/application/dtos/consumo_mqtt_dto.py — Respuesta del consumo MQTT por hora (#93)."""

from datetime import datetime

from pydantic import BaseModel, Field


class ConsumoMqttHoraDTO(BaseModel):
    hora: datetime
    mensajes: int
    bytes_payload: int


class ConsumoMqttResponseDTO(BaseModel):
    device_uid: str
    desde: datetime
    hasta: datetime
    total_mensajes: int
    total_bytes_payload: int
    horas: list[ConsumoMqttHoraDTO]
    nota: str = Field(
        default="Bytes de payload que llegaron al servidor. No es el consumo del chip: lo mide el operador.",
    )
