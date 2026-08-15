from datetime import datetime

from pydantic import BaseModel, ConfigDict


class OrganizacionBaseDTO(BaseModel):
    nombre: str
    plan_id: str | None = None
    cuit: str | None = None
    email_contacto: str | None = None
    telefono_contacto: str | None = None


class OrganizacionCreateDTO(OrganizacionBaseDTO):
    pass


class OrganizacionResponseDTO(OrganizacionBaseDTO):
    id: str
    creado_en: datetime
    actualizado_en: datetime
    model_config = ConfigDict(from_attributes=True)


class PlantaBaseDTO(BaseModel):
    organizacion_id: str
    nombre: str
    direccion: str | None = None
    latitud: float | None = None
    longitud: float | None = None


class PlantaCreateDTO(PlantaBaseDTO):
    pass


class PlantaResponseDTO(PlantaBaseDTO):
    id: str
    creado_en: datetime
    actualizado_en: datetime
    model_config = ConfigDict(from_attributes=True)
