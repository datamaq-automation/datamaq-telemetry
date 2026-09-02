
from pydantic import BaseModel, ConfigDict

from src.application.dtos.tipos import FechaHoraUTC


class AlertaResolverRequestDTO(BaseModel):
    observaciones: str | None = None


class AlertaResponseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dispositivo_id: str
    tipo_alerta: str
    severidad: str
    mensaje: str
    esta_resuelta: bool
    disparada_en: FechaHoraUTC
    resuelta_en: FechaHoraUTC | None = None
    fase: str | None = None
    valor_medido: float | None = None
    valor_umbral: float | None = None
    unidad: str | None = None
    categoria: str | None = None
    duracion_segundos: float | None = None
    observaciones: str | None = None
