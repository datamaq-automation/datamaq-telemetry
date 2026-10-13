"""src/application/dtos/activo_unifilar_dto.py — DTOs para la gestión de activos unifilares mutables (arquitectura híbrida)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.application.dtos.planta_estructura_dto import NodoUnifilarDTO

TipoActivoUnifilarLiteral = Literal[
    "TRANSFORMADOR",
    "TGBT",
    "TABLERO_SECCIONAL",
    "LINEA",
    "MAQUINA",
    "CARGA_VIRTUAL",
]


class ActivoUnifilarDTO(BaseModel):
    """Representación de un nodo o activo unifilar mutable persistido en MySQL."""

    id: str
    planta_id: str
    nombre: str
    tipo: TipoActivoUnifilarLiteral
    tension_nominal_v: float
    parent_id: str | None = None
    device_id: str | None = None
    potencia_nominal_kw: float | None = None
    capacidad_nominal_kva: float | None = None
    categoria_uso: str | None = None
    uso_significativo: bool = False
    posicion_x: float | None = None
    posicion_y: float | None = None
    ancho: float | None = None
    alto: float | None = None
    orden: int = 0
    creado_en: datetime
    actualizado_en: datetime

    model_config = ConfigDict(from_attributes=True)


class CrearActivoUnifilarDTO(BaseModel):
    """Payload para la creación de un nuevo activo unifilar mutable."""

    id: str | None = Field(default=None, description="Identificador único. Si se omite, se genera automáticamente.")
    planta_id: str
    nombre: str
    tipo: TipoActivoUnifilarLiteral
    tension_nominal_v: float
    parent_id: str | None = None
    device_id: str | None = None
    potencia_nominal_kw: float | None = None
    capacidad_nominal_kva: float | None = None
    categoria_uso: str | None = None
    uso_significativo: bool = False
    posicion_x: float | None = None
    posicion_y: float | None = None
    ancho: float | None = None
    alto: float | None = None
    orden: int = 0


class ActualizarActivoUnifilarDTO(BaseModel):
    """Payload para actualización parcial de un activo unifilar mutable."""

    nombre: str | None = None
    tipo: TipoActivoUnifilarLiteral | None = None
    tension_nominal_v: float | None = None
    parent_id: str | None = None
    device_id: str | None = None
    potencia_nominal_kw: float | None = None
    capacidad_nominal_kva: float | None = None
    categoria_uso: str | None = None
    uso_significativo: bool | None = None
    posicion_x: float | None = None
    posicion_y: float | None = None
    ancho: float | None = None
    alto: float | None = None
    orden: int | None = None


class JerarquiaHibridaPlantaDTO(BaseModel):
    """Jerarquía unificada de unifilar combinando GitOps inmutable y MySQL mutable."""

    planta_id: str
    nodos_inmutables: list[NodoUnifilarDTO] = Field(default_factory=list)
    activos_mutables: list[ActivoUnifilarDTO] = Field(default_factory=list)
    nodos_unificados: list[NodoUnifilarDTO] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
