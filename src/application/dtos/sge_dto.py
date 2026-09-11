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
