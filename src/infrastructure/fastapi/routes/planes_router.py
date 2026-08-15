from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from src.adapters.controllers.planes_controller import PlanesController
from src.adapters.presenters.error_presenter import ErrorPresenter
from src.application.dtos.plan_dto import PlanCreateDTO, PlanResponseDTO
from src.infrastructure.fastapi.dependencies import get_planes_controller

router = APIRouter(prefix="/api", tags=["Planes de Telemetría"])


@router.get("/planes", response_model=list[PlanResponseDTO])
def list_planes(
    controller: Annotated[PlanesController, Depends(get_planes_controller)],
    solo_publicos: bool = False,
):
    return controller.listar_planes(solo_publicos=solo_publicos)


@router.post("/planes", response_model=PlanResponseDTO)
def create_plan(
    dto: PlanCreateDTO,
    controller: Annotated[PlanesController, Depends(get_planes_controller)],
):
    try:
        return controller.crear_plan(dto)
    except Exception as e:
        code, err = ErrorPresenter.presentar_excepcion(e)
        raise HTTPException(status_code=code, detail=err["mensaje"]) from e
