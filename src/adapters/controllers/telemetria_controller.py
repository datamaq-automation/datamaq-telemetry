from datetime import datetime
from typing import Any

from src.application.dtos.telemetria_dto import (
    AcumuladoEnergiaDTO,
    LecturaInstantaneaDTO,
    TelemetriaLatestResponseDTO,
)
from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.application.use_cases.ingestar_telemetria import IngestarTelemetriaUseCase


class TelemetriaController:
    def __init__(
        self,
        consultar_uc: ConsultarTelemetriaUseCase,
        ingestar_uc: IngestarTelemetriaUseCase,
    ):
        self.consultar_uc = consultar_uc
        self.ingestar_uc = ingestar_uc

    def obtener_ultima(self, id_o_uid: str) -> TelemetriaLatestResponseDTO:
        return self.consultar_uc.obtener_ultima_telemetria(id_o_uid)

    def listar_instantaneas(
        self, id_o_uid: str, limite: int = 100, desde: datetime | None = None
    ) -> list[LecturaInstantaneaDTO]:
        return self.consultar_uc.listar_instantaneas(id_o_uid, limite, desde)

    def listar_energias(
        self, id_o_uid: str, limite: int = 100, desde: datetime | None = None
    ) -> list[AcumuladoEnergiaDTO]:
        return self.consultar_uc.listar_energias(id_o_uid, limite, desde)

    def procesar_mensaje_mqtt(self, topico: str, payload: dict[str, Any]) -> None:
        self.ingestar_uc.ejecutar(topico, payload)
