"""src/infrastructure/fastapi/routes/dispositivos_router.py."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from src.application.dtos.audit_dto import RegistrarAuditLogDTO
from src.application.dtos.dispositivo_dto import (
    DispositivoCreateDTO,
    DispositivoResponseDTO,
    DispositivoUpdateDTO,
)
from src.application.use_cases.gestionar_auditoria import RegistrarEventoAuditoriaUseCase
from src.application.use_cases.gestionar_dispositivos import GestionarDispositivosUseCase
from src.infrastructure.fastapi.dependencies import (
    get_dispositivos_use_case,
    get_mqtt_listener,
    get_registrar_auditoria_use_case,
    get_usuario_actual,
    requiere_rol_escritura,
)
from src.infrastructure.fastapi.device_ownership import verificar_propiedad_dispositivo
from src.infrastructure.fastapi.error_handler import manejar_error_http
from src.infrastructure.fastapi.planta_ownership import resolver_planta_permitida

router = APIRouter(
    prefix="/api/v1/dispositivos",
    tags=["Dispositivos"],
    dependencies=[Depends(get_usuario_actual)],
)

PlantaPermitida = Annotated[str | None, Depends(resolver_planta_permitida)]


@router.get("", response_model=list[DispositivoResponseDTO])
def list_dispositivos(
    use_case: Annotated[GestionarDispositivosUseCase, Depends(get_dispositivos_use_case)],
    claims: Annotated[dict, Depends(get_usuario_actual)],
    planta_id: PlantaPermitida,
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


def _auditar_cambios_dispositivo(
    audit_use_case: RegistrarEventoAuditoriaUseCase | None,
    dev_previo: object | None,
    dto: DispositivoUpdateDTO,
    device_id: str,
    claims: dict | None,
    request: Request | None,
) -> None:
    if audit_use_case is None or dev_previo is None:
        return
    ip = request.client.host if request and request.client else None
    user_agent = request.headers.get("User-Agent") if request else None
    actor_id = claims.get("sub") if claims else None
    actor_email = claims.get("usuario") if claims else None

    # 1. Cambios de calibración técnica
    campos_calibracion = (
        "tipo_instalacion",
        "fases_con_ti",
        "ct_fases_invertidas",
        "correccion_angular_fases",
    )
    cambios_calibracion = {
        c: {"anterior": getattr(dev_previo, c, None), "nuevo": getattr(dto, c, None)}
        for c in campos_calibracion
        if getattr(dto, c, None) is not None and getattr(dto, c, None) != getattr(dev_previo, c, None)
    }
    if cambios_calibracion:
        try:
            audit_use_case.ejecutar(
                RegistrarAuditLogDTO(
                    categoria="METROLOGIA",
                    accion="CALIBRACION_ACTUALIZADA",
                    resultado="EXITO",
                    actor_usuario_id=actor_id,
                    actor_email=actor_email,
                    actor_ip=ip,
                    actor_user_agent=user_agent,
                    recurso_tipo="dispositivo",
                    recurso_id=device_id,
                    metadatos=cambios_calibracion,
                )
            )
        except Exception:
            pass

    # 2. Cambio de tarifa
    prev_tarifa = getattr(dev_previo, "categoria_tarifaria", None)
    if dto.categoria_tarifaria is not None and dto.categoria_tarifaria != prev_tarifa:
        try:
            audit_use_case.ejecutar(
                RegistrarAuditLogDTO(
                    categoria="METROLOGIA",
                    accion="TARIFA_ACTUALIZADA",
                    resultado="EXITO",
                    actor_usuario_id=actor_id,
                    actor_email=actor_email,
                    actor_ip=ip,
                    actor_user_agent=user_agent,
                    recurso_tipo="dispositivo",
                    recurso_id=device_id,
                    metadatos={
                        "categoria_tarifaria": {
                            "anterior": prev_tarifa,
                            "nuevo": dto.categoria_tarifaria,
                        }
                    },
                )
            )
        except Exception:
            pass


@router.put("/{device_id}", response_model=DispositivoResponseDTO, dependencies=[Depends(requiere_rol_escritura)])
@router.patch("/{device_id}", response_model=DispositivoResponseDTO, dependencies=[Depends(requiere_rol_escritura)])
def update_dispositivo(
    device_id: str,
    dto: DispositivoUpdateDTO,
    use_case: Annotated[GestionarDispositivosUseCase, Depends(get_dispositivos_use_case)],
    claims: Annotated[dict | None, Depends(get_usuario_actual)] = None,
    audit_use_case: Annotated[RegistrarEventoAuditoriaUseCase | None, Depends(get_registrar_auditoria_use_case)] = None,
    request: Request = None,  # type: ignore[assignment]
):
    try:
        dev_previo = None
        if audit_use_case is not None:
            try:
                dev_previo = use_case.obtener_dispositivo(device_id)
            except Exception:
                dev_previo = None

        resultado = use_case.actualizar_dispositivo(device_id, dto)
        _auditar_cambios_dispositivo(audit_use_case, dev_previo, dto, device_id, claims, request)
        return resultado
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
