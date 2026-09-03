from pydantic import BaseModel, ConfigDict, Field

from src.application.dtos.tipos import FechaHoraUTC


class EventoDisponibilidadResponseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    maquina_id: str
    estado: str
    tipo_parada: str | None = None
    inicio_at: FechaHoraUTC
    fin_at: FechaHoraUTC | None = None
    potencia_promedio_w: float | None = None
    origen: str
    corregido_por_usuario_id: str | None = None
    corregido_at: FechaHoraUTC | None = None
    comentario: str | None = None
    duracion_segundos: float | None = None


class CorregirClasificacionRequestDTO(BaseModel):
    tipo_parada: str = Field(..., description="PROGRAMADA, NO_PROGRAMADA o SIN_CLASIFICAR")
    comentario: str | None = None


class ParadaProgramadaCreateDTO(BaseModel):
    maquina_id: str
    inicio_at: FechaHoraUTC
    fin_at: FechaHoraUTC
    motivo: str = Field(..., min_length=1, max_length=250)


class ParadaProgramadaResponseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    maquina_id: str
    inicio_at: FechaHoraUTC
    fin_at: FechaHoraUTC
    motivo: str
    creado_por_usuario_id: str | None = None
    creado_en: FechaHoraUTC
