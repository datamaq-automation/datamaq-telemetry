from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from src.adapters.controllers.dispositivos_controller import DispositivosController
from src.adapters.presenters.error_presenter import ErrorPresenter
from src.application.dtos.dispositivo_dto import (
    DispositivoCreateDTO,
    DispositivoResponseDTO,
    DispositivoUpdateDTO,
)
from src.infrastructure.fastapi.dependencies import get_dispositivos_controller

router = APIRouter(prefix="/api/dispositivos", tags=["Dispositivos"])


@router.get("", response_model=list[DispositivoResponseDTO])
def list_dispositivos(
    controller: Annotated[DispositivosController, Depends(get_dispositivos_controller)],
    planta_id: str | None = None,
):
    return controller.listar_dispositivos(planta_id)


@router.get("/{device_id}", response_model=DispositivoResponseDTO)
def get_dispositivo(
    device_id: str,
    controller: Annotated[DispositivosController, Depends(get_dispositivos_controller)],
):
    try:
        return controller.obtener_dispositivo(device_id)
    except Exception as e:
        code, err = ErrorPresenter.presentar_excepcion(e)
        raise HTTPException(status_code=code, detail=err["mensaje"]) from e


@router.post("", response_model=DispositivoResponseDTO)
def register_dispositivo(
    dto: DispositivoCreateDTO,
    controller: Annotated[DispositivosController, Depends(get_dispositivos_controller)],
):
    try:
        return controller.registrar_dispositivo(dto)
    except Exception as e:
        code, err = ErrorPresenter.presentar_excepcion(e)
        raise HTTPException(status_code=code, detail=err["mensaje"]) from e


@router.put("/{device_id}", response_model=DispositivoResponseDTO)
def update_dispositivo(
    device_id: str,
    dto: DispositivoUpdateDTO,
    controller: Annotated[DispositivosController, Depends(get_dispositivos_controller)],
):
    try:
        return controller.actualizar_dispositivo(device_id, dto)
    except Exception as e:
        code, err = ErrorPresenter.presentar_excepcion(e)
        raise HTTPException(status_code=code, detail=err["mensaje"]) from e
