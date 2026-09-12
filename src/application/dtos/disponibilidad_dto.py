"""src/application/dtos/disponibilidad_dto.py."""
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


class MetricasDisponibilidadOEEResponseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    maquina_id: str
    periodo_inicio: FechaHoraUTC
    periodo_fin: FechaHoraUTC
    tiempo_total_segundos: float
    tiempo_marcha_segundos: float
    tiempo_parada_programada_segundos: float
    tiempo_parada_no_programada_segundos: float
    disponibilidad_oee_porcentaje: float
    mtbf_horas: float | None = None
    mttr_horas: float | None = None
    cantidad_paradas_no_programadas: int = 0
    cantidad_paradas_programadas: int = 0
    cantidad_ciclos_marcha: int = 0
