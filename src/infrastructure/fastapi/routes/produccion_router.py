"""src/infrastructure/fastapi/routes/produccion_router.py — Endpoints para sensórica de proceso y SEC híbrido."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status

from src.adapters.gateways.in_memory_variables_proceso_repository import (
    InMemoryVariablesProcesoRepository,
)
from src.application.dtos.produccion_dto import (
    LecturaProcesoRequestDTO,
    LecturaProcesoResponseDTO,
)
from src.application.mappers.produccion_mapper import lectura_to_dto
from src.application.use_cases.registrar_lectura_proceso import RegistrarLecturaProcesoUseCase
from src.domain.produccion.ports import RepositorioVariablesProcesoPort
from src.infrastructure.fastapi.dependencies import get_usuario_actual
from src.infrastructure.fastapi.error_handler import manejar_error_http

_repo_proceso_singleton: RepositorioVariablesProcesoPort = InMemoryVariablesProcesoRepository()


def get_variables_proceso_repository() -> RepositorioVariablesProcesoPort:
    return _repo_proceso_singleton


def get_registrar_lectura_use_case(
    repo: Annotated[RepositorioVariablesProcesoPort, Depends(get_variables_proceso_repository)],
) -> RegistrarLecturaProcesoUseCase:
    return RegistrarLecturaProcesoUseCase(repo_proceso=repo)


router = APIRouter(
    prefix="/api/v1/produccion",
    tags=["Producción & EnPI"],
    dependencies=[Depends(get_usuario_actual)],
)


@router.post(
    "/lecturas",
    response_model=LecturaProcesoResponseDTO,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
    summary="Ingestar lectura de sensórica de proceso (sensor inductivo de corte o metros)",
)
def registrar_lectura(
    dto: LecturaProcesoRequestDTO,
    use_case: Annotated[
        RegistrarLecturaProcesoUseCase,
        Depends(get_registrar_lectura_use_case),
    ],
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
) -> LecturaProcesoResponseDTO:
    """Registra una lectura discreta o acumulada de un sensor de proceso industrial."""
    try:
        lectura = use_case.ejecutar(
            maquina_id=dto.maquina_id,
            momento=dto.momento,
            variable_tipo=dto.variable_tipo,
            delta_valor=dto.delta_valor,
            valor_acumulado=dto.valor_acumulado,
        )
        return lectura_to_dto(lectura, maquina_id=dto.maquina_id)
    except Exception as exc:
        manejar_error_http(exc)
