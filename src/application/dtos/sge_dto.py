"""src/application/dtos/sge_dto.py."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CategoriaSgeDTO = Literal[
    "politica",
    "operacion",
    "mantenimiento",
    "normativa_enre",
    "metas_enpi",
]


class SgeDocArticleDTO(BaseModel):
    id: str
    titulo: str
    categoria: CategoriaSgeDTO
    roles_permitidos: list[str] = Field(alias="rolesPermitidos")
    resumen: str
    puntos_clave: list[str] = Field(alias="puntosClave")
    acciones_inmediatas: list[str] = Field(alias="accionesInmediatas")
    referencia_iso: str = Field(alias="referenciaIso")
    documento_url: str | None = Field(default=None, alias="documentoUrl")

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )


class AcuseCapacitacionRequestDTO(BaseModel):
    articulo_id: str = Field(alias="articuloId")
    version_doc: str = Field(alias="versionDoc")
    comentarios: str | None = None

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )


class RegistroCapacitacionResponseDTO(BaseModel):
    id: str
    usuario_id: str = Field(alias="usuarioId")
    articulo_id: str = Field(alias="articuloId")
    rol_usuario: str = Field(alias="rolUsuario")
    fecha_completado: str = Field(alias="fechaCompletado")
    version_doc: str = Field(alias="versionDoc")
    comentarios: str | None = None

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )


class EstadoCompetenciasUsuarioDTO(BaseModel):
    usuario_id: str = Field(alias="usuarioId")
    rol_usuario: str = Field(alias="rolUsuario")
    capacitaciones_completadas: list[RegistroCapacitacionResponseDTO] = Field(alias="capacitacionesCompletadas")
    capacitaciones_pendientes: list[SgeDocArticleDTO] = Field(alias="capacitacionesPendientes")
    porcentaje_cumplimiento: float = Field(alias="porcentajeCumplimiento")

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
    )
