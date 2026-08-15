from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AlertaResponseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dispositivo_id: str
    tipo_alerta: str
    severidad: str
    mensaje: str
    esta_resuelta: bool
    disparada_en: datetime
    resuelta_en: datetime | None = None
