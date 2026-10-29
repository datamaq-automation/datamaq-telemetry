"""src/application/use_cases/consultar_consumo_mqtt.py — Consulta de solo lectura del consumo MQTT por hora (#93)."""

from datetime import datetime

from src.application.dtos.consumo_mqtt_dto import ConsumoMqttHoraDTO, ConsumoMqttResponseDTO
from src.application.ports.consumo_mqtt_port import RepositorioConsumoMqttPort
from src.domain.telemetria.servicios.consumo_mqtt import normalizar_uid


class ConsultarConsumoMqttUseCase:
    def __init__(self, repo: RepositorioConsumoMqttPort) -> None:
        self.repo = repo

    def ejecutar(self, device_uid: str, desde: datetime, hasta: datetime) -> ConsumoMqttResponseDTO:
        if desde >= hasta:
            raise ValueError("desde debe ser anterior a hasta")
        uid = normalizar_uid(device_uid)
        filas = self.repo.consultar(uid, desde, hasta)
        horas = [ConsumoMqttHoraDTO(hora=h, mensajes=m, bytes_payload=b) for h, m, b in filas]
        return ConsumoMqttResponseDTO(
            device_uid=uid,
            desde=desde,
            hasta=hasta,
            total_mensajes=sum(h.mensajes for h in horas),
            total_bytes_payload=sum(h.bytes_payload for h in horas),
            horas=horas,
        )
