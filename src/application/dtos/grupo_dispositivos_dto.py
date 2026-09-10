from pydantic import BaseModel, ConfigDict

from src.application.dtos.telemetria_dto import EnergiaAgregadaDTO
from src.application.dtos.tipos import FechaHoraUTC


class GrupoDispositivosCreateDTO(BaseModel):
    planta_id: str
    nombre: str
    dispositivos_ids: list[str] = []


class GrupoDispositivosResponseDTO(BaseModel):
    id: str
    planta_id: str
    nombre: str
    dispositivos_ids: list[str]
    creado_en: FechaHoraUTC
    actualizado_en: FechaHoraUTC
    model_config = ConfigDict(from_attributes=True)


class AgregarMiembroGrupoDTO(BaseModel):
    dispositivo_id: str


class ResumenGrupoDispositivosDTO(BaseModel):
    grupo_id: str
    potencia_activa_total_w: float | None = None
    dispositivos_sin_dato: list[str] = []
    energia_agregada: list[EnergiaAgregadaDTO] = []
