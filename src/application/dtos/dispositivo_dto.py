from pydantic import BaseModel, ConfigDict, Field

from src.application.dtos.tipos import FechaHoraUTC


class DispositivoBaseDTO(BaseModel):
    device_uid: str
    nombre: str = "Nuevo Powermeter"
    modelo: str = "SmartPlus"
    planta_id: str | None = None
    numero_serie: str | None = None
    version_hw: str | None = None
    version_fw: str | None = None
    ubicacion_tag: str | None = None
    esta_activo: bool = True
    tipo_instalacion: str = "CONSUMO"
    fases_con_ti: str = "R,S,T"


class DispositivoCreateDTO(DispositivoBaseDTO):
    pass


class DispositivoUpdateDTO(BaseModel):
    nombre: str | None = Field(None, min_length=1, max_length=120)
    ubicacion_tag: str | None = Field(None, max_length=150)
    numero_serie: str | None = Field(None, max_length=100)
    tipo_instalacion: str | None = Field(None, description="3P4W, 3P3W, 1P2W, CONSUMO, GENERACION")
    fases_con_ti: str | None = Field(None, description="R,S,T o S,T o R,T")
    esta_activo: bool | None = None
    planta_id: str | None = None


DispositivoActualizarDTO = DispositivoUpdateDTO


class DispositivoResponseDTO(DispositivoBaseDTO):
    id: str
    estado: str
    visto_por_ultima_vez: FechaHoraUTC | None = None
    creado_en: FechaHoraUTC
    actualizado_en: FechaHoraUTC
    voltage_linea_V: float | None = None
    model_config = ConfigDict(from_attributes=True)
