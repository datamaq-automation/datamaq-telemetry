from pydantic import BaseModel, ConfigDict, Field

from src.application.dtos.tipos import FechaHoraUTC


class MaquinaBaseDTO(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=120)
    dispositivo_id: str


class MaquinaCreateDTO(MaquinaBaseDTO):
    pass


class MaquinaUpdateDTO(BaseModel):
    nombre: str | None = Field(None, min_length=1, max_length=120)
    umbral_marcha_w: float | None = Field(None, ge=0.0)
    ventana_persistencia_lecturas: int | None = Field(None, ge=1)
    ventana_persistencia_segundos: float | None = Field(None, ge=0.0)


class MaquinaResponseDTO(MaquinaBaseDTO):
    id: str
    umbral_marcha_w: float | None = None
    ventana_persistencia_lecturas: int
    ventana_persistencia_segundos: float
    esta_calibrada: bool
    creado_en: FechaHoraUTC
    actualizado_en: FechaHoraUTC
    model_config = ConfigDict(from_attributes=True)


class HistogramaPotenciaResponseDTO(BaseModel):
    dispositivo_id: str
    dias_analizados: int
    cantidad_lecturas: int
    bordes_bins_w: list[float]
    frecuencias: list[int]
    umbral_sugerido_w: float | None = None
