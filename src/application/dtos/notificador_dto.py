"""src/application/dtos/notificador_dto.py."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotificadorEstadoDTO(BaseModel):
    """Estado actual de la alarma de potencia Tuya."""

    alarma_activa: bool = Field(alias="alarmaActiva")
    potencia_adquirida_w: float = Field(alias="potenciaAdquiridaW")
    potencia_contratada_w: float = Field(alias="potenciaContratadaW")
    porcentaje_uso: float = Field(alias="porcentajeUso")
    ultimo_evento: datetime = Field(alias="ultimoEvento")

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )
