"""src/infrastructure/fastapi/routes/dispositivos_router.py."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.application.dtos.dispositivo_dto import (
    DispositivoCreateDTO,
    DispositivoResponseDTO,
    DispositivoUpdateDTO,
)
from src.application.use_cases.gestionar_dispositivos import GestionarDispositivosUseCase
from src.infrastructure.fastapi.dependencies import (
    get_dispositivos_use_case,
    get_mqtt_listener,
    get_usuario_actual,
    requiere_rol_escritura,
)
from src.infrastructure.fastapi.device_ownership import verificar_propiedad_dispositivo
from src.infrastructure.fastapi.error_handler import manejar_error_http

router = APIRouter(
    prefix="/api/v1/dispositivos",
    tags=["Dispositivos"],
    dependencies=[Depends(get_usuario_actual)],
)


@router.get("", response_model=list[DispositivoResponseDTO])
def list_dispositivos(
    use_case: Annotated[GestionarDispositivosUseCase, Depends(get_dispositivos_use_case)],
    claims: Annotated[dict, Depends(get_usuario_actual)],
    planta_id: str | None = None,
):
    rol = claims.get("rol")
    if rol in ("superadmin", "invitado_global"):
        organizacion_id = None
    else:
        organizacion_id = claims.get("org")
        if organizacion_id is None:
            # Sin organización asignada: no hay nada que listar (fail-closed).
            return []
    return use_case.listar_dispositivos(planta_id, organizacion_id=organizacion_id)


@router.get(
    "/{device_id}",
    response_model=DispositivoResponseDTO,
    dependencies=[Depends(verificar_propiedad_dispositivo)],
)
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
@router.patch("/{device_id}", response_model=DispositivoResponseDTO, dependencies=[Depends(requiere_rol_escritura)])
def update_dispositivo(
    device_id: str,
    dto: DispositivoUpdateDTO,
    use_case: Annotated[GestionarDispositivosUseCase, Depends(get_dispositivos_use_case)],
):
    try:
        return use_case.actualizar_dispositivo(device_id, dto)
    except Exception as e:
        manejar_error_http(e)


@router.post("/{device_id}/realtime")
def activate_realtime_mode(
    device_id: str,
    use_case: Annotated[GestionarDispositivosUseCase, Depends(get_dispositivos_use_case)],
    segundos: int = Query(120, ge=10, le=600),
):
    try:
        disp = use_case.obtener_dispositivo(device_id)
        listener = get_mqtt_listener()
        enviado = False
        if listener:
            enviado = listener.activar_tiempo_real_dispositivo(disp.device_uid, segundos=segundos)
        return {
            "status": "ok" if enviado else "mqtt_offline",
            "device_id": disp.id,
            "device_uid": disp.device_uid,
            "tiempo_real_activado": enviado,
            "segundos": segundos,
        }
    except Exception as e:
        manejar_error_http(e)
