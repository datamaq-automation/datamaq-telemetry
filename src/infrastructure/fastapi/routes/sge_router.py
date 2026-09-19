"""src/infrastructure/fastapi/routes/sge_router.py."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from src.adapters.gateways.in_memory_documentacion_sge_repository import (
    InMemoryDocumentacionSgeRepository,
)
from src.adapters.gateways.in_memory_registro_capacitaciones_sge_repository import (
    InMemoryRegistroCapacitacionesSgeRepository,
)
from src.application.dtos.sge_dto import (
    AcuseCapacitacionRequestDTO,
    EstadoCompetenciasUsuarioDTO,
    RegistroCapacitacionResponseDTO,
    SgeDocArticleDTO,
)
from src.application.mappers.sge_mapper import (
    articulo_to_dto,
    estado_to_dto,
    registro_to_dto,
)
from src.application.use_cases.consultar_competencias_usuario import (
    ConsultarCompetenciasUsuarioUseCase,
)
from src.application.use_cases.consultar_documentacion_sge import (
    ConsultarDocumentacionSgeUseCase,
)
from src.application.use_cases.registrar_acuse_capacitacion import (
    RegistrarAcuseCapacitacionUseCase,
)
from src.domain.sge.ports import (
    RepositorioDocumentacionSgePort,
    RepositorioRegistroCapacitacionesSgePort,
)
from src.infrastructure.fastapi.dependencies import get_usuario_actual
from src.infrastructure.fastapi.error_handler import manejar_error_http

_repositorio_sge_singleton: RepositorioDocumentacionSgePort = InMemoryDocumentacionSgeRepository()
_repositorio_capacitaciones_singleton: RepositorioRegistroCapacitacionesSgePort = (
    InMemoryRegistroCapacitacionesSgeRepository()
)


def get_documentacion_sge_repository() -> RepositorioDocumentacionSgePort:
    return _repositorio_sge_singleton


def get_registro_capacitaciones_repository() -> RepositorioRegistroCapacitacionesSgePort:
    return _repositorio_capacitaciones_singleton


def get_consultar_documentacion_sge_use_case(
    repo: Annotated[
        RepositorioDocumentacionSgePort,
        Depends(get_documentacion_sge_repository),
    ],
) -> ConsultarDocumentacionSgeUseCase:
    return ConsultarDocumentacionSgeUseCase(repositorio=repo)


def get_registrar_acuse_use_case(
    repo_doc: Annotated[
        RepositorioDocumentacionSgePort,
        Depends(get_documentacion_sge_repository),
    ],
    repo_cap: Annotated[
        RepositorioRegistroCapacitacionesSgePort,
        Depends(get_registro_capacitaciones_repository),
    ],
) -> RegistrarAcuseCapacitacionUseCase:
    return RegistrarAcuseCapacitacionUseCase(
        repo_documentacion=repo_doc,
        repo_capacitaciones=repo_cap,
    )


def get_consultar_competencias_use_case(
    repo_doc: Annotated[
        RepositorioDocumentacionSgePort,
        Depends(get_documentacion_sge_repository),
    ],
    repo_cap: Annotated[
        RepositorioRegistroCapacitacionesSgePort,
        Depends(get_registro_capacitaciones_repository),
    ],
) -> ConsultarCompetenciasUsuarioUseCase:
    return ConsultarCompetenciasUsuarioUseCase(
        repo_documentacion=repo_doc,
        repo_capacitaciones=repo_cap,
    )


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


@router.post(
    "/competencias/acuse",
    response_model=RegistroCapacitacionResponseDTO,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar acuse y evidencia de capacitación o toma de conciencia (ISO 50001 §7.2)",
)
def registrar_acuse_capacitacion(
    dto: AcuseCapacitacionRequestDTO,
    use_case: Annotated[
        RegistrarAcuseCapacitacionUseCase,
        Depends(get_registrar_acuse_use_case),
    ],
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
) -> RegistroCapacitacionResponseDTO:
    """Registra de forma inmutable la evidencia de capacitación del usuario autenticado."""
    try:
        usuario_id = str(claims.get("sub", ""))
        rol_usuario = str(claims.get("rol", "operador"))
        registro = use_case.ejecutar(
            usuario_id=usuario_id,
            articulo_id=dto.articulo_id,
            rol_usuario=rol_usuario,
            version_doc=dto.version_doc,
            comentarios=dto.comentarios,
        )
        return registro_to_dto(registro)
    except Exception as exc:
        manejar_error_http(exc)


@router.get(
    "/competencias/mis-capacitaciones",
    response_model=EstadoCompetenciasUsuarioDTO,
    response_model_by_alias=True,
    summary="Consultar estado de competencias y capacitaciones pendientes (ISO 50001 §7.2)",
)
def consultar_mis_competencias(
    use_case: Annotated[
        ConsultarCompetenciasUsuarioUseCase,
        Depends(get_consultar_competencias_use_case),
    ],
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
) -> EstadoCompetenciasUsuarioDTO:
    """Retorna el consolidado de capacitaciones completadas, pendientes y porcentaje de cumplimiento."""
    try:
        usuario_id = str(claims.get("sub", ""))
        rol_usuario = str(claims.get("rol", "operador"))
        estado = use_case.ejecutar(usuario_id=usuario_id, rol_usuario=rol_usuario)
        return estado_to_dto(estado)
    except Exception as exc:
        manejar_error_http(exc)
