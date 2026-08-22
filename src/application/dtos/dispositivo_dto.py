from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
    nombre: str | None = None
    planta_id: str | None = None
    ubicacion_tag: str | None = None
    esta_activo: bool | None = None
    tipo_instalacion: str | None = None
    fases_con_ti: str | None = None


class DispositivoResponseDTO(DispositivoBaseDTO):
    id: str
    estado: str
    visto_por_ultima_vez: datetime | None = None
    creado_en: datetime
    actualizado_en: datetime
    model_config = ConfigDict(from_attributes=True)
