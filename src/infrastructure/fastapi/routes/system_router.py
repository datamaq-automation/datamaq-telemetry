from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends

from src.application.dtos.purga_dto import PurgaRequestDTO, PurgaResultadoDTO
from src.application.use_cases.purgar_telemetria import PurgarTelemetriaExpiradaUseCase
from src.infrastructure.fastapi.dependencies import (
    get_mqtt_listener,
    get_purga_use_case,
    requiere_rol_admin,
)
from src.infrastructure.fastapi.error_handler import manejar_error_http

router = APIRouter(tags=["Sistema"])


@router.get("/health")
def health_check():
    listener = get_mqtt_listener()
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mqtt_conectado": listener.esta_conectado() if listener else False,
    }


@router.post("/api/system/purge", response_model=PurgaResultadoDTO)
def trigger_purge(
    claims: Annotated[dict, Depends(requiere_rol_admin)],
    use_case: Annotated[PurgarTelemetriaExpiradaUseCase, Depends(get_purga_use_case)],
    dto: PurgaRequestDTO | None = None,
):
    try:
        req = dto or PurgaRequestDTO()
        return use_case.ejecutar(req)
    except Exception as e:
        manejar_error_http(e)
