"""src/infrastructure/fastapi/routes/alertas_router.py."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query

from src.application.dtos.alerta_dto import AlertaResolverRequestDTO, AlertaResponseDTO
from src.application.use_cases.gestionar_alertas import GestionarAlertasUseCase
from src.infrastructure.fastapi.dependencies import (
    get_alertas_use_case,
    get_usuario_actual,
    requiere_rol_escritura,
)
from src.infrastructure.fastapi.device_ownership import verificar_propiedad_alerta
from src.infrastructure.fastapi.error_handler import manejar_error_http

router = APIRouter(
    prefix="/api/v1/alertas",
    tags=["Alertas"],
    dependencies=[Depends(get_usuario_actual)],
)


@router.get("", response_model=list[AlertaResponseDTO])
def list_alertas(
    use_case: Annotated[GestionarAlertasUseCase, Depends(get_alertas_use_case)],
    claims: Annotated[dict, Depends(get_usuario_actual)],
    device_id: str | None = Query(None, description="Filtrar por UUID de dispositivo"),
    solo_abiertas: bool = Query(False, description="Filtrar solo alertas no resueltas"),
    severidad: str | None = Query(None, description="Filtrar por severidad (INFO, WARNING, CRITICAL)"),
    limit: int = Query(100, le=500, description="Límite de registros"),
    desde: datetime | None = Query(None, description="Fecha de inicio ISO8601"),
    hasta: datetime | None = Query(None, description="Fecha de fin ISO8601"),
):
    # Roles globales ven todas; el resto, solo las de su organización (un device_id ajeno da []).
    organizacion_id = None
    if claims.get("rol") not in ("superadmin", "invitado_global"):
        organizacion_id = claims.get("org")
        if not organizacion_id:
            return []  # Sin organización asignada: fail-closed, como GET /dispositivos.
    return use_case.listar_alertas(
        dispositivo_id=device_id,
        solo_abiertas=solo_abiertas,
        severidad=severidad,
        limite=limit,
        desde=desde,
        hasta=hasta,
        organizacion_id=organizacion_id,
    )


@router.post(
    "/{alerta_id}/resolver",
    response_model=AlertaResponseDTO,
    dependencies=[Depends(requiere_rol_escritura), Depends(verificar_propiedad_alerta)],
)
@router.patch(
    "/{alerta_id}/resolver",
    response_model=AlertaResponseDTO,
    dependencies=[Depends(requiere_rol_escritura), Depends(verificar_propiedad_alerta)],
)
def resolve_alerta(
    alerta_id: int,
    use_case: Annotated[GestionarAlertasUseCase, Depends(get_alertas_use_case)],
    body: AlertaResolverRequestDTO | None = Body(None),
):
    try:
        return use_case.resolver_alerta(alerta_id, observaciones=body.observaciones if body else None)
    except Exception as e:
        manejar_error_http(e)
