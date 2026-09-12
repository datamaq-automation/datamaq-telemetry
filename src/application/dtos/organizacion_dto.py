"""src/application/dtos/organizacion_dto.py."""

from pydantic import BaseModel, ConfigDict

from src.application.dtos.tipos import FechaHoraUTC


class OrganizacionBaseDTO(BaseModel):
    nombre: str
    plan_id: str | None = None
    cuit: str | None = None
    email_contacto: str | None = None
    telefono_contacto: str | None = None
    pro_vence_en: FechaHoraUTC | None = None
    modo_free: str = "PRIVADO_BASICO"


class OrganizacionCreateDTO(OrganizacionBaseDTO):
    pass


class OrganizacionResponseDTO(OrganizacionBaseDTO):
    id: str
    creado_en: FechaHoraUTC
    actualizado_en: FechaHoraUTC
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
    creado_en: FechaHoraUTC
    actualizado_en: FechaHoraUTC
    model_config = ConfigDict(from_attributes=True)
