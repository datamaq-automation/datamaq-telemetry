"""src/infrastructure/fastapi/routes/system_router.py."""
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from src.application.dtos.purga_dto import PurgaRequestDTO, PurgaResultadoDTO
from src.application.use_cases.purgar_telemetria import PurgarTelemetriaExpiradaUseCase
from src.infrastructure.fastapi.dependencies import (
    get_mqtt_listener,
    get_purga_use_case,
    requiere_rol_admin,
)
from src.infrastructure.fastapi.error_handler import manejar_error_http
from src.infrastructure.sqlalchemy.database import (
    verificar_conexion_db,
    verificar_estado_migraciones,
)

router = APIRouter(tags=["Sistema"])


@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@router.get("/health/live")
def liveness_check():
    """Sonda de liveness: valida que el proceso está activo."""
    return {
        "status": "alive",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/ready")
def readiness_check(response: Response):
    """Sonda de readiness: valida que la BD esté conectada y en la versión correcta de migración."""
    listener = get_mqtt_listener()
    db_ok = verificar_conexion_db()
    migraciones = verificar_estado_migraciones()

    esta_listo = db_ok and migraciones.get("sincronizado", False)
    if not esta_listo:
        response.status_code = 503
        return {
            "status": "not_ready",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "database_conectada": db_ok,
            "migraciones": migraciones,
            "mqtt_conectado": listener.esta_conectado() if listener else False,
        }

    return {
        "status": "ready",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database_conectada": db_ok,
        "migraciones": migraciones,
        "mqtt_conectado": listener.esta_conectado() if listener else False,
    }


@router.get("/health")
def health_check(response: Response):
    """Chequeo general de salud (compatibilidad con monitores heredados)."""
    return readiness_check(response)


@router.get("/api/v1/system/ws-status")
def websocket_status():
    """Estado y métricas de observabilidad de los WebSockets en vivo."""
    from src.infrastructure.fastapi.server import obtener_metricas_ws

    listener = get_mqtt_listener()
    metricas = obtener_metricas_ws()
    metricas["mqtt_conectado"] = listener.esta_conectado() if listener else False
    return metricas


@router.post("/api/v1/system/purge", response_model=PurgaResultadoDTO)
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
