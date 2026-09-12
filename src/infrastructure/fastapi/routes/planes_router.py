"""src/infrastructure/fastapi/routes/planes_router.py."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.application.dtos.plan_dto import PlanCreateDTO, PlanResponseDTO
from src.application.use_cases.gestionar_planes import GestionarPlanesUseCase
from src.infrastructure.fastapi.dependencies import (
    get_planes_use_case,
    get_usuario_actual,
    requiere_rol_escritura,
)
from src.infrastructure.fastapi.error_handler import manejar_error_http

router = APIRouter(
    prefix="/api/v1",
    tags=["Planes de Telemetría"],
    dependencies=[Depends(get_usuario_actual)],
)


@router.get("/planes", response_model=list[PlanResponseDTO])
def list_planes(
    use_case: Annotated[GestionarPlanesUseCase, Depends(get_planes_use_case)],
    solo_publicos: bool = False,
):
    return use_case.listar_catalogo(solo_publicos=solo_publicos)


@router.post("/planes", response_model=PlanResponseDTO, dependencies=[Depends(requiere_rol_escritura)])
def create_plan(
    dto: PlanCreateDTO,
    use_case: Annotated[GestionarPlanesUseCase, Depends(get_planes_use_case)],
):
    try:
        return use_case.crear_plan(dto)
    except Exception as e:
        manejar_error_http(e)
