from typing import Annotated

from fastapi import APIRouter, Depends

from src.adapters.controllers.dispositivos_controller import DispositivosController
from src.application.dtos.organizacion_dto import (
    OrganizacionCreateDTO,
    OrganizacionResponseDTO,
    PlantaCreateDTO,
    PlantaResponseDTO,
)
from src.infrastructure.fastapi.dependencies import get_dispositivos_controller, get_usuario_actual
from src.infrastructure.fastapi.error_handler import manejar_error_http

router = APIRouter(
    prefix="/api",
    tags=["Organizaciones y Plantas"],
    dependencies=[Depends(get_usuario_actual)],
)


@router.get("/organizaciones", response_model=list[OrganizacionResponseDTO])
def list_organizaciones(
    controller: Annotated[DispositivosController, Depends(get_dispositivos_controller)],
):
    return controller.listar_organizaciones()


@router.post("/organizaciones", response_model=OrganizacionResponseDTO)
def create_organizacion(
    dto: OrganizacionCreateDTO,
    controller: Annotated[DispositivosController, Depends(get_dispositivos_controller)],
):
    try:
        return controller.crear_organizacion(dto)
    except Exception as e:
        manejar_error_http(e)


@router.get("/plantas", response_model=list[PlantaResponseDTO])
def list_plantas(
    controller: Annotated[DispositivosController, Depends(get_dispositivos_controller)],
    organizacion_id: str | None = None,
):
    return controller.listar_plantas(organizacion_id)


@router.post("/plantas", response_model=PlantaResponseDTO)
def create_planta(
    dto: PlantaCreateDTO,
    controller: Annotated[DispositivosController, Depends(get_dispositivos_controller)],
):
    try:
        return controller.crear_planta(dto)
    except Exception as e:
        manejar_error_http(e)
