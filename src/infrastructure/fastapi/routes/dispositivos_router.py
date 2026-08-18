from typing import Annotated

from fastapi import APIRouter, Depends

from src.application.dtos.dispositivo_dto import (
    DispositivoCreateDTO,
    DispositivoResponseDTO,
    DispositivoUpdateDTO,
)
from src.application.use_cases.gestionar_dispositivos import GestionarDispositivosUseCase
from src.infrastructure.fastapi.dependencies import (
    get_dispositivos_use_case,
    get_usuario_actual,
    requiere_rol_escritura,
)
from src.infrastructure.fastapi.error_handler import manejar_error_http

router = APIRouter(
    prefix="/api/dispositivos",
    tags=["Dispositivos"],
    dependencies=[Depends(get_usuario_actual)],
)


@router.get("", response_model=list[DispositivoResponseDTO])
def list_dispositivos(
    use_case: Annotated[GestionarDispositivosUseCase, Depends(get_dispositivos_use_case)],
    planta_id: str | None = None,
):
    return use_case.listar_dispositivos(planta_id)


@router.get("/{device_id}", response_model=DispositivoResponseDTO)
def get_dispositivo(
    device_id: str,
    use_case: Annotated[GestionarDispositivosUseCase, Depends(get_dispositivos_use_case)],
):
    try:
        return use_case.obtener_dispositivo(device_id)
    except Exception as e:
        manejar_error_http(e)


@router.post("", response_model=DispositivoResponseDTO, dependencies=[Depends(requiere_rol_escritura)])
def register_dispositivo(
    dto: DispositivoCreateDTO,
    use_case: Annotated[GestionarDispositivosUseCase, Depends(get_dispositivos_use_case)],
):
    try:
        return use_case.registrar_dispositivo(dto)
    except Exception as e:
        manejar_error_http(e)


@router.put("/{device_id}", response_model=DispositivoResponseDTO, dependencies=[Depends(requiere_rol_escritura)])
def update_dispositivo(
    device_id: str,
    dto: DispositivoUpdateDTO,
    use_case: Annotated[GestionarDispositivosUseCase, Depends(get_dispositivos_use_case)],
):
    try:
        return use_case.actualizar_dispositivo(device_id, dto)
    except Exception as e:
        manejar_error_http(e)
