"""src/infrastructure/fastapi/routes/system_router.py."""

import json
import os
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from src.application.dtos.build_info_dto import BuildInfoResponseDTO
from src.application.dtos.purga_dto import PurgaRequestDTO, PurgaResultadoDTO
from src.application.use_cases.purgar_telemetria import PurgarTelemetriaExpiradaUseCase
from src.infrastructure.fastapi.dependencies import (
    get_mqtt_listener,
    get_purga_use_case,
    requiere_rol_admin,
)
from src.infrastructure.fastapi.error_handler import manejar_error_http
from src.infrastructure.settings.config import Settings, get_settings
from src.infrastructure.sqlalchemy.database import (
    verificar_conexion_db,
    verificar_estado_migraciones,
)
from src.infrastructure.yaml.loaders import cargar_organizaciones_completas

router = APIRouter(tags=["Sistema"])


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

    esta_listo = db_ok and migraciones.get("sincronizado", False) and data_ok.get("valido", False)
    if not esta_listo:
        response.status_code = 503
        return {
            "status": "not_ready",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "database_conectada": db_ok,
            "migraciones": migraciones,
            "mqtt_conectado": listener.esta_conectado() if listener else False,
            "datamaq_data": data_ok,
        }

    return {
        "status": "ready",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database_conectada": db_ok,
        "migraciones": migraciones,
        "mqtt_conectado": listener.esta_conectado() if listener else False,
        "datamaq_data": data_ok,
    }


@router.get("/health")
def health_check(response: Response):
    """Chequeo general de salud (compatibilidad con monitores heredados)."""
    return readiness_check(response)


VALOR_BUILD_DESCONOCIDO = "desconocido"


def _leer_build_info(ruta_archivo: str) -> dict[str, str]:
    """Lee build_info.json de forma segura sin excepciones no controladas."""
    try:
        if not os.path.isfile(ruta_archivo):
            return {"commit": VALOR_BUILD_DESCONOCIDO, "rama": VALOR_BUILD_DESCONOCIDO}
        with open(ruta_archivo, encoding="utf-8") as f:
            datos = json.load(f)
        if not isinstance(datos, dict):
            return {"commit": VALOR_BUILD_DESCONOCIDO, "rama": VALOR_BUILD_DESCONOCIDO}

        commit = datos.get("commit")
        rama = datos.get("rama")

        if not isinstance(commit, str) or not commit.strip():
            commit_str = VALOR_BUILD_DESCONOCIDO
        elif commit.strip() == VALOR_BUILD_DESCONOCIDO:
            commit_str = VALOR_BUILD_DESCONOCIDO
        else:
            commit_str = commit.strip()[:7]

        if not isinstance(rama, str) or not rama.strip():
            rama_str = VALOR_BUILD_DESCONOCIDO
        else:
            rama_str = rama.strip()

        return {"commit": commit_str, "rama": rama_str}
    except Exception:
        return {"commit": VALOR_BUILD_DESCONOCIDO, "rama": VALOR_BUILD_DESCONOCIDO}


@router.get("/health/build", response_model=BuildInfoResponseDTO)
def health_build(settings: Annotated[Settings, Depends(get_settings)]) -> BuildInfoResponseDTO:
    """Retorna información de la versión construida (commit y rama)."""
    info = _leer_build_info(settings.ruta_build_info)
    return BuildInfoResponseDTO(commit=info["commit"], rama=info["rama"])


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
