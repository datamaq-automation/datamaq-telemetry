"""src/infrastructure/fastapi/routes/system_router.py."""

import os
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
from src.infrastructure.yaml.loaders import cargar_organizaciones_completas
from src.version import __version__

router = APIRouter(tags=["Sistema"])

_FECHA_INICIO_PROCESO = datetime.now(timezone.utc).isoformat()


def _obtener_fecha_despliegue() -> str:
    return os.getenv("DEPLOY_DATE") or os.getenv("FECHA_DESPLIEGUE") or _FECHA_INICIO_PROCESO


def _obtener_commit() -> str:
    env_commit = os.getenv("GIT_COMMIT") or os.getenv("COMMIT_SHA")
    if env_commit:
        return env_commit[:7]
    try:
        raiz_repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../"))
        git_dir = os.path.join(raiz_repo, ".git")
        head_file = os.path.join(git_dir, "HEAD")
        if os.path.exists(head_file):
            with open(head_file, encoding="utf-8") as f:
                ref = f.read().strip()
            if ref.startswith("ref: "):
                ref_path = os.path.join(git_dir, ref[5:])
                if os.path.exists(ref_path):
                    with open(ref_path, encoding="utf-8") as rf:
                        return rf.read().strip()[:7]
            else:
                return ref[:7]
    except Exception:
        pass
    return "unknown"


def _validar_datamaq_data() -> dict:
    """Valida que datamaq-data se cargó correctamente (≥1 org, ≥1 planta total)."""
    try:
        data_dir = os.path.join(os.path.dirname(__file__), "../../../../data")
        if not os.path.isdir(data_dir):
            return {"valido": False, "razon": "directorio_data_no_existe"}
        organizaciones = cargar_organizaciones_completas(data_dir)
        if not organizaciones:
            return {"valido": False, "razon": "sin_organizaciones"}
        total_plantas = sum(len(org.get("plantas", [])) for org in organizaciones)
        if total_plantas == 0:
            return {"valido": False, "razon": "sin_plantas"}
        return {
            "valido": True,
            "organizaciones": len(organizaciones),
            "plantas_totales": total_plantas,
        }
    except Exception as e:
        return {"valido": False, "razon": f"excepcion: {e!s}"}


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
    """Sonda de readiness: valida BD, migraciones y datamaq-data."""
    listener = get_mqtt_listener()
    db_ok = verificar_conexion_db()
    migraciones = verificar_estado_migraciones()
    data_ok = _validar_datamaq_data()
    mqtt_ok = listener.esta_conectado() if listener else False

    esta_listo = db_ok and migraciones.get("sincronizado", False) and data_ok.get("valido", False)
    if not esta_listo:
        response.status_code = 503
        return {
            "status": "not_ready",
            "version": __version__,
            "commit": _obtener_commit(),
            "fecha_despliegue": _obtener_fecha_despliegue(),
            "mysql_conectado": db_ok,
            "mqtt_conectado": mqtt_ok,
            "database_conectada": db_ok,
            "migraciones": migraciones,
            "datamaq_data": data_ok,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "status": "ready",
        "version": __version__,
        "commit": _obtener_commit(),
        "fecha_despliegue": _obtener_fecha_despliegue(),
        "mysql_conectado": db_ok,
        "mqtt_conectado": mqtt_ok,
        "database_conectada": db_ok,
        "migraciones": migraciones,
        "datamaq_data": data_ok,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health")
def health_check(response: Response):
    """Chequeo general de salud (compatibilidad con monitores heredados)."""
    return readiness_check(response)


@router.get("/version")
def version_info():
    """Devuelve metadatos de versión, commit y estado operativo de servicios."""
    listener = get_mqtt_listener()
    db_ok = verificar_conexion_db()
    mqtt_ok = listener.esta_conectado() if listener else False
    return {
        "version": __version__,
        "commit": _obtener_commit(),
        "fecha_despliegue": _obtener_fecha_despliegue(),
        "mysql_conectado": db_ok,
        "mqtt_conectado": mqtt_ok,
        "status": "ready" if db_ok else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


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
