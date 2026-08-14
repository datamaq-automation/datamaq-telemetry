from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from src.adapters.controllers.telemetria_controller import TelemetriaController
from src.adapters.presenters.error_presenter import ErrorPresenter
from src.application.dtos.telemetria_dto import (
    AcumuladoEnergiaDTO,
    LecturaInstantaneaDTO,
    TelemetriaLatestResponseDTO,
)
from src.infrastructure.fastapi.dependencies import get_telemetria_controller

router = APIRouter(prefix="/api/telemetria", tags=["Telemetría"])


@router.get("/latest/{device_id}", response_model=TelemetriaLatestResponseDTO)
def get_latest_telemetry(
    device_id: str,
    controller: Annotated[TelemetriaController, Depends(get_telemetria_controller)],
):
    try:
        return controller.obtener_ultima(device_id)
    except Exception as e:
        code, err = ErrorPresenter.presentar_excepcion(e)
        raise HTTPException(status_code=code, detail=err["mensaje"]) from e


@router.get("/instantaneous/{device_id}", response_model=list[LecturaInstantaneaDTO])
def get_instantaneous_history(
    device_id: str,
    controller: Annotated[TelemetriaController, Depends(get_telemetria_controller)],
    limit: int = Query(100, le=1000),
    hours: int | None = Query(None, description="Últimas N horas"),
):
    try:
        desde = datetime.now(timezone.utc) - timedelta(hours=hours) if hours else None
        return controller.listar_instantaneas(device_id, limit, desde)
    except Exception as e:
        code, err = ErrorPresenter.presentar_excepcion(e)
        raise HTTPException(status_code=code, detail=err["mensaje"]) from e


@router.get("/energy/{device_id}", response_model=list[AcumuladoEnergiaDTO])
def get_energy_history(
    device_id: str,
    controller: Annotated[TelemetriaController, Depends(get_telemetria_controller)],
    limit: int = Query(100, le=1000),
    days: int | None = Query(None, description="Últimos N días"),
):
    try:
        desde = datetime.now(timezone.utc) - timedelta(days=days) if days else None
        return controller.listar_energias(device_id, limit, desde)
    except Exception as e:
        code, err = ErrorPresenter.presentar_excepcion(e)
        raise HTTPException(status_code=code, detail=err["mensaje"]) from e
