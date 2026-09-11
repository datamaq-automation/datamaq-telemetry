from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from src.adapters.gateways.in_memory_documentacion_sge_repository import (
    InMemoryDocumentacionSgeRepository,
)
from src.application.dtos.sge_dto import SgeDocArticleDTO
from src.application.mappers.sge_mapper import articulo_to_dto
from src.application.use_cases.consultar_documentacion_sge import (
    ConsultarDocumentacionSgeUseCase,
)
from src.domain.sge.ports import RepositorioDocumentacionSgePort
from src.infrastructure.fastapi.dependencies import get_usuario_actual
from src.infrastructure.fastapi.error_handler import manejar_error_http

_repositorio_sge_singleton: RepositorioDocumentacionSgePort = InMemoryDocumentacionSgeRepository()


def get_documentacion_sge_repository() -> RepositorioDocumentacionSgePort:
    return _repositorio_sge_singleton


def get_consultar_documentacion_sge_use_case(
    repo: Annotated[
        RepositorioDocumentacionSgePort,
        Depends(get_documentacion_sge_repository),
    ],
) -> ConsultarDocumentacionSgeUseCase:
    return ConsultarDocumentacionSgeUseCase(repositorio=repo)


router = APIRouter(
    prefix="/api/v1/sge",
    tags=["SGE - ISO 50001"],
    dependencies=[Depends(get_usuario_actual)],
)


@router.get(
    "/documentacion",
    response_model=list[SgeDocArticleDTO],
    response_model_by_alias=True,
    summary="Consultar documentación operativa SGE según el rol del usuario autenticado",
)
def obtener_documentacion_sge(
    use_case: Annotated[
        ConsultarDocumentacionSgeUseCase,
        Depends(get_consultar_documentacion_sge_use_case),
    ],
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    rol: str | None = Query(
        None,
        description="Previsualizar documentación como otro rol (permitido para administradores y auditores)",
    ),
) -> list[SgeDocArticleDTO]:
    """Retorna los procedimientos, instructivos y políticas del SGE ISO 50001 correspondientes."""
    try:
        rol_usuario = str(claims.get("rol", "operador"))
        articulos = use_case.ejecutar(rol_usuario=rol_usuario, rol_filtro=rol)
        return [articulo_to_dto(a) for a in articulos]
    except Exception as exc:
        manejar_error_http(exc)
