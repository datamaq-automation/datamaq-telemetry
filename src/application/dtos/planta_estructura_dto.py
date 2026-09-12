"""src/application/dtos/planta_estructura_dto.py."""

from pydantic import BaseModel, ConfigDict, Field


class NodoUnifilarDTO(BaseModel):
    id: str
    parent_id: str | None = None
    nombre: str
    tipo: str  # acometida, transformador, tgbt, seccional, carga
    device_id: str | None = None
    tension_nominal_V: float
    capacidad_nominal_kVA: float | None = None
    orden: int = 0
    model_config = ConfigDict(from_attributes=True)


class UnifilarPlantaDTO(BaseModel):
    planta_id: str
    nombre_planta: str
    nodos: list[NodoUnifilarDTO] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


class GuardarUnifilarRequestDTO(BaseModel):
    nodos: list[NodoUnifilarDTO]


class CoordenadasZonaDTO(BaseModel):
    x_porcentaje: float = Field(ge=0.0, le=100.0)
    y_porcentaje: float = Field(ge=0.0, le=100.0)
    ancho_porcentaje: float = Field(ge=0.0, le=100.0)
    alto_porcentaje: float = Field(ge=0.0, le=100.0)


class ZonaPlantaDTO(BaseModel):
    id: str
    nombre: str
    coordenadas: CoordenadasZonaDTO
    model_config = ConfigDict(from_attributes=True)


class PosicionLayoutDTO(BaseModel):
    x_porcentaje: float = Field(ge=0.0, le=100.0)
    y_porcentaje: float = Field(ge=0.0, le=100.0)


class DispositivoLayoutDTO(BaseModel):
    device_id: str
    zona_id: str | None = None
    posicion: PosicionLayoutDTO
    model_config = ConfigDict(from_attributes=True)


class LayoutPlantaDTO(BaseModel):
    planta_id: str
    nombre_planta: str
    plano_svg_url: str | None = None
    zonas: list[ZonaPlantaDTO] = Field(default_factory=list)
    dispositivos: list[DispositivoLayoutDTO] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


class GuardarLayoutRequestDTO(BaseModel):
    plano_svg_url: str | None = None
    zonas: list[ZonaPlantaDTO] = Field(default_factory=list)
    dispositivos: list[DispositivoLayoutDTO] = Field(default_factory=list)
