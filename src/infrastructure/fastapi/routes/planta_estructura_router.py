"""src/infrastructure/fastapi/routes/planta_estructura_router.py."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.application.dtos.planta_estructura_dto import (
    LayoutPlantaDTO,
    PlantaAreasEstadisticasResponseDTO,
    PuntoPotenciaNodoUnifilarDTO,
    ResumenNodoUnifilarDTO,
    UnifilarPlantaDTO,
)
from src.application.use_cases.consultar_nodo_unifilar import ConsultarNodoUnifilarUseCase
from src.application.use_cases.gestionar_planta_estructura import (
    GestionarPlantaEstructuraUseCase,
)
from src.infrastructure.fastapi.dependencies import (
    get_consultar_nodo_unifilar_use_case,
    get_planta_estructura_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.error_handler import manejar_error_http

router = APIRouter(
    prefix="/api/v1",
    tags=["Diagrama Unifilar y Layout de Planta"],
    dependencies=[Depends(get_usuario_actual)],
)


def _resolver_org_id(claims: dict) -> str | None:
    rol = claims.get("rol")
    if rol in ("superadmin", "invitado_global"):
        return None
    return claims.get("org")


# --- Diagrama Unifilar ---


@router.get("/planta/unifilar", response_model=UnifilarPlantaDTO)
def get_unifilar_default(
    use_case: Annotated[GestionarPlantaEstructuraUseCase, Depends(get_planta_estructura_use_case)],
    claims: Annotated[dict, Depends(get_usuario_actual)],
    planta_id: str | None = None,
):
    try:
        org_id = _resolver_org_id(claims)
        return use_case.obtener_unifilar(planta_id=planta_id, organizacion_id=org_id)
    except Exception as e:
        manejar_error_http(e)


@router.get("/plantas/{planta_id}/unifilar", response_model=UnifilarPlantaDTO)
def get_unifilar_by_planta(
    planta_id: str,
    use_case: Annotated[GestionarPlantaEstructuraUseCase, Depends(get_planta_estructura_use_case)],
):
    try:
        return use_case.obtener_unifilar(planta_id=planta_id)
    except Exception as e:
        manejar_error_http(e)


@router.get("/plantas/{planta_id}/unifilar/nodos/{nodo_id}/resumen", response_model=ResumenNodoUnifilarDTO)
def resumen_nodo_unifilar(
    planta_id: str,
    nodo_id: str,
    use_case: Annotated[ConsultarNodoUnifilarUseCase, Depends(get_consultar_nodo_unifilar_use_case)],
    claims: Annotated[dict, Depends(get_usuario_actual)],
    granularity: str = "day",
    timezone: str = "America/Argentina/Buenos_Aires",
    dias: int | None = None,
):
    try:
        org_id = _resolver_org_id(claims)
        return use_case.resumen(planta_id, nodo_id, org_id, granularity, timezone, dias)
    except Exception as e:
        manejar_error_http(e)


@router.get(
    "/plantas/{planta_id}/unifilar/nodos/{nodo_id}/resumen/historico",
    response_model=list[PuntoPotenciaNodoUnifilarDTO],
)
def historico_nodo_unifilar(
    planta_id: str,
    nodo_id: str,
    use_case: Annotated[ConsultarNodoUnifilarUseCase, Depends(get_consultar_nodo_unifilar_use_case)],
    claims: Annotated[dict, Depends(get_usuario_actual)],
    hours: int = 24,
    granularity: str = "5m",
):
    try:
        org_id = _resolver_org_id(claims)
        return use_case.historico(planta_id, nodo_id, org_id, granularity, hours)
    except Exception as e:
        manejar_error_http(e)


# --- Layout de Planta ---


@router.get("/planta/layout", response_model=LayoutPlantaDTO)
def get_layout_default(
    use_case: Annotated[GestionarPlantaEstructuraUseCase, Depends(get_planta_estructura_use_case)],
    claims: Annotated[dict, Depends(get_usuario_actual)],
    planta_id: str | None = None,
):
    try:
        org_id = _resolver_org_id(claims)
        return use_case.obtener_layout(planta_id=planta_id, organizacion_id=org_id)
    except Exception as e:
        manejar_error_http(e)


@router.get("/plantas/{planta_id}/layout", response_model=LayoutPlantaDTO)
def get_layout_by_planta(
    planta_id: str,
    use_case: Annotated[GestionarPlantaEstructuraUseCase, Depends(get_planta_estructura_use_case)],
):
    try:
        return use_case.obtener_layout(planta_id=planta_id)
    except Exception as e:
        manejar_error_http(e)


# --- Estadísticas de Áreas (ISA-95 Nivel 2) ---


@router.get("/planta/areas", response_model=PlantaAreasEstadisticasResponseDTO)
def get_areas_estadisticas_default(
    use_case: Annotated[GestionarPlantaEstructuraUseCase, Depends(get_planta_estructura_use_case)],
    claims: Annotated[dict, Depends(get_usuario_actual)],
    planta_id: str | None = None,
):
    try:
        org_id = _resolver_org_id(claims)
        return use_case.obtener_areas_estadisticas(planta_id=planta_id, organizacion_id=org_id)
    except Exception as e:
        manejar_error_http(e)


@router.get("/plantas/{planta_id}/areas", response_model=PlantaAreasEstadisticasResponseDTO)
def get_areas_estadisticas_by_planta(
    planta_id: str,
    use_case: Annotated[GestionarPlantaEstructuraUseCase, Depends(get_planta_estructura_use_case)],
):
    try:
        return use_case.obtener_areas_estadisticas(planta_id=planta_id)
    except Exception as e:
        manejar_error_http(e)
