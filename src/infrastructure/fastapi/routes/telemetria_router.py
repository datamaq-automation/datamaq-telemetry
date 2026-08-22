from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.application.dtos.telemetria_dto import (
    AcumuladoEnergiaDTO,
    LecturaInstantaneaDTO,
    TelemetriaLatestResponseDTO,
)
from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.infrastructure.fastapi.dependencies import get_telemetria_use_case, get_usuario_actual
from src.infrastructure.fastapi.error_handler import manejar_error_http

router = APIRouter(
    prefix="/api/telemetria",
    tags=["Telemetría"],
    dependencies=[Depends(get_usuario_actual)],
)


@router.get("/latest/{device_id}", response_model=TelemetriaLatestResponseDTO)
def get_latest_telemetry(
    device_id: str,
    use_case: Annotated[ConsultarTelemetriaUseCase, Depends(get_telemetria_use_case)],
):
    try:
        return use_case.obtener_ultima_telemetria(device_id)
    except Exception as e:
        manejar_error_http(e)


@router.get("/instantaneous/{device_id}", response_model=list[LecturaInstantaneaDTO])
def get_instantaneous_history(
    device_id: str,
    use_case: Annotated[ConsultarTelemetriaUseCase, Depends(get_telemetria_use_case)],
    limit: int = Query(500, ge=1, le=5000, description="Límite máximo de registros a retornar"),
    hours: int | None = Query(None, ge=1, le=720, description="Últimas N horas"),
    granularity: str = Query("auto", description="Granularidad temporal: auto, raw, 1m, 5m, 15m, 1h"),
):
    try:
        desde = datetime.now(timezone.utc) - timedelta(hours=hours) if hours else None
        return use_case.listar_instantaneas(
            id_o_uid=device_id,
            limite=limit,
            desde=desde,
            granularidad=granularity,
            horas=hours,
        )
    except Exception as e:
        manejar_error_http(e)


@router.get("/energy/{device_id}", response_model=list[AcumuladoEnergiaDTO])
def get_energy_history(
    device_id: str,
    use_case: Annotated[ConsultarTelemetriaUseCase, Depends(get_telemetria_use_case)],
    limit: int = Query(100, le=1000),
    days: int | None = Query(None, description="Últimos N días"),
):
    try:
        desde = datetime.now(timezone.utc) - timedelta(days=days) if days else None
        return use_case.listar_energias(device_id, limit, desde)
    except Exception as e:
        manejar_error_http(e)
