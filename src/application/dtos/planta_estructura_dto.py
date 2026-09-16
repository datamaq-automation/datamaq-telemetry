"""src/application/dtos/planta_estructura_dto.py."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.application.dtos.telemetria_dto import EnergiaAgregadaDTO
from src.application.dtos.tipos import FechaHoraUTC

TipoNodoUnifilarLiteral = Literal["acometida", "transformador", "tgbt", "seccional", "carga"]


class NodoUnifilarDTO(BaseModel):
    id: str
    parent_id: str | None = None
    nombre: str
    tipo: TipoNodoUnifilarLiteral
    device_id: str | None = None
    es_virtual: bool = False
    # R-03: nombre de la máquina asociada 1:1 al medidor (`machines.device_id` UNIQUE), si existe.
    nombre_maquina: str | None = None
    tension_nominal_V: float
    capacidad_nominal_kVA: float | None = None
    potencia_nominal_kw: float | None = None
    uso_significativo: bool = False
    categoria_uso: str | None = None
    variable_relevante: str | None = None
    orden: int = 0
    fuente_dato: str | None = None
    notas_metrologicas: str | None = None
    model_config = ConfigDict(from_attributes=True)


class UnifilarPlantaDTO(BaseModel):
    planta_id: str
    nombre_planta: str
    nodos: list[NodoUnifilarDTO] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


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


class AreaEstadisticasDTO(BaseModel):
    area_id: str
    nombre: str
    superficie_m2: float | None = None
    lineas_count: int = 0
    dispositivos_activos_count: int = 0
    dispositivos_total_count: int = 0
    carga_promedio_kw: float = 0.0
    dispositivo_ids: list[str] = Field(default_factory=list)
    coordenadas_layout: CoordenadasZonaDTO | None = None
    model_config = ConfigDict(from_attributes=True)


class PlantaAreasEstadisticasResponseDTO(BaseModel):
    planta_id: str
    superficie_total_m2: float | None = None
    areas: list[AreaEstadisticasDTO] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


class ResumenNodoUnifilarDTO(BaseModel):
    planta_id: str
    nodo_id: str
    es_virtual: bool
    dispositivos_ids: list[str] = Field(default_factory=list)
    potencia_activa_total_w: float | None = None
    potencia_reactiva_total_var: float | None = None
    potencia_aparente_total_va: float | None = None
    factor_desplazamiento_total: float | None = None
    dispositivos_sin_dato: list[str] = Field(default_factory=list)
    energia_agregada: list[EnergiaAgregadaDTO] = Field(default_factory=list)


class PuntoPotenciaNodoUnifilarDTO(BaseModel):
    momento: FechaHoraUTC
    potencia_activa_total_w: float | None = None
    potencia_reactiva_total_var: float | None = None
    potencia_aparente_total_va: float | None = None
    factor_desplazamiento_total: float | None = None
    dispositivos_sin_dato: list[str] = Field(default_factory=list)
