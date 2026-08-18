from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.application.dtos.alerta_dto import AlertaResponseDTO
from src.application.use_cases.gestionar_alertas import GestionarAlertasUseCase
from src.infrastructure.fastapi.dependencies import (
    get_alertas_use_case,
    get_usuario_actual,
    requiere_rol_escritura,
)
from src.infrastructure.fastapi.error_handler import manejar_error_http

router = APIRouter(
    prefix="/api/alertas",
    tags=["Alertas"],
    dependencies=[Depends(get_usuario_actual)],
)


@router.get("", response_model=list[AlertaResponseDTO])
def list_alertas(
    use_case: Annotated[GestionarAlertasUseCase, Depends(get_alertas_use_case)],
    device_id: str | None = Query(None, description="Filtrar por UUID de dispositivo"),
    solo_abiertas: bool = Query(False, description="Filtrar solo alertas no resueltas"),
    limit: int = Query(100, le=500, description="Límite de registros"),
):
    return use_case.listar_alertas(
        dispositivo_id=device_id,
        solo_abiertas=solo_abiertas,
        limite=limit,
    )


@router.post("/{alerta_id}/resolver", response_model=AlertaResponseDTO, dependencies=[Depends(requiere_rol_escritura)])
def resolve_alerta(
    alerta_id: int,
    use_case: Annotated[GestionarAlertasUseCase, Depends(get_alertas_use_case)],
):
    try:
        return use_case.resolver_alerta(alerta_id)
    except Exception as e:
        manejar_error_http(e)
