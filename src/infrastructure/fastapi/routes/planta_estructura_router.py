"""src/infrastructure/fastapi/routes/planta_estructura_router.py."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from src.application.dtos.planta_estructura_dto import (
    LayoutPlantaDTO,
    PlantaAreasEstadisticasResponseDTO,
    PuntoPotenciaNodoUnifilarDTO,
    ResumenNodoUnifilarDTO,
    UnifilarPlantaDTO,
)
from src.application.dtos.tipos import FechaHoraUTC
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
from src.infrastructure.fastapi.headers_historico import (
    HEADER_DATOS_DESDE,
    formatear_datos_desde,
    setear_potencia_referencia,
)
from src.infrastructure.fastapi.planta_ownership import resolver_planta_permitida

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


# Planta efectiva ya verificada contra la política de acceso (404 si no está permitida).
PlantaPermitida = Annotated[str | None, Depends(resolver_planta_permitida)]


# --- Diagrama Unifilar ---


@router.get("/planta/unifilar", response_model=UnifilarPlantaDTO)
def get_unifilar_default(
    use_case: Annotated[GestionarPlantaEstructuraUseCase, Depends(get_planta_estructura_use_case)],
    claims: Annotated[dict, Depends(get_usuario_actual)],
    planta_id: PlantaPermitida,
):
    try:
        org_id = _resolver_org_id(claims)
        return use_case.obtener_unifilar(planta_id=planta_id, organizacion_id=org_id)
    except Exception as e:
        manejar_error_http(e)


@router.get(
    "/plantas/{planta_id}/unifilar", response_model=UnifilarPlantaDTO, dependencies=[Depends(resolver_planta_permitida)]
)
def get_unifilar_by_planta(
    planta_id: str,
    use_case: Annotated[GestionarPlantaEstructuraUseCase, Depends(get_planta_estructura_use_case)],
    claims: Annotated[dict, Depends(get_usuario_actual)],
):
    try:
        return use_case.obtener_unifilar(planta_id=planta_id, organizacion_id=_resolver_org_id(claims))
    except Exception as e:
        manejar_error_http(e)


@router.get(
    "/plantas/{planta_id}/unifilar/nodos/{nodo_id}/resumen",
    response_model=ResumenNodoUnifilarDTO,
    dependencies=[Depends(resolver_planta_permitida)],
)
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
    dependencies=[Depends(resolver_planta_permitida)],
)
def historico_nodo_unifilar(
    planta_id: str,
    nodo_id: str,
    use_case: Annotated[ConsultarNodoUnifilarUseCase, Depends(get_consultar_nodo_unifilar_use_case)],
    claims: Annotated[dict, Depends(get_usuario_actual)],
    response: Response,
    hours: int = Query(24, ge=1, le=720, description="Ancho de la ventana en horas"),
    granularity: str = "5m",
    hasta: FechaHoraUTC | None = Query(
        None, description="Fin de la ventana ISO8601 UTC; la ventana es [hasta - hours, hasta]. Sin valor: ahora"
    ),
):
    """El header `X-Datos-Desde` informa el corte de retención más reciente entre los medidores
    frontera; se omite si el nodo no tiene medidores. `X-Potencia-Referencia-W` es el P99 de la
    serie sumada en los últimos 30 días (omitido sin datos suficientes), independiente de la ventana."""
    try:
        org_id = _resolver_org_id(claims)
        historico = use_case.historico(planta_id, nodo_id, org_id, granularity, hours, hasta)
        if historico.datos_desde is not None:
            response.headers[HEADER_DATOS_DESDE] = formatear_datos_desde(historico.datos_desde)
        # Después de `historico`: la caché se consulta solo si el nodo ya pasó el control de acceso.
        setear_potencia_referencia(
            response,
            ("nodo", org_id, planta_id, nodo_id),
            lambda: use_case.potencia_referencia(planta_id, nodo_id, org_id),
        )
        return historico.puntos
    except Exception as e:
        manejar_error_http(e)


# --- Layout de Planta ---


@router.get("/planta/layout", response_model=LayoutPlantaDTO)
def get_layout_default(
    use_case: Annotated[GestionarPlantaEstructuraUseCase, Depends(get_planta_estructura_use_case)],
    claims: Annotated[dict, Depends(get_usuario_actual)],
    planta_id: PlantaPermitida,
):
    try:
        org_id = _resolver_org_id(claims)
        return use_case.obtener_layout(planta_id=planta_id, organizacion_id=org_id)
    except Exception as e:
        manejar_error_http(e)


@router.get(
    "/plantas/{planta_id}/layout", response_model=LayoutPlantaDTO, dependencies=[Depends(resolver_planta_permitida)]
)
def get_layout_by_planta(
    planta_id: str,
    use_case: Annotated[GestionarPlantaEstructuraUseCase, Depends(get_planta_estructura_use_case)],
    claims: Annotated[dict, Depends(get_usuario_actual)],
):
    try:
        return use_case.obtener_layout(planta_id=planta_id, organizacion_id=_resolver_org_id(claims))
    except Exception as e:
        manejar_error_http(e)


# --- Estadísticas de Áreas (ISA-95 Nivel 2) ---


@router.get("/planta/areas", response_model=PlantaAreasEstadisticasResponseDTO)
def get_areas_estadisticas_default(
    use_case: Annotated[GestionarPlantaEstructuraUseCase, Depends(get_planta_estructura_use_case)],
    claims: Annotated[dict, Depends(get_usuario_actual)],
    planta_id: PlantaPermitida,
):
    try:
        org_id = _resolver_org_id(claims)
        return use_case.obtener_areas_estadisticas(planta_id=planta_id, organizacion_id=org_id)
    except Exception as e:
        manejar_error_http(e)


@router.get(
    "/plantas/{planta_id}/areas",
    response_model=PlantaAreasEstadisticasResponseDTO,
    dependencies=[Depends(resolver_planta_permitida)],
)
def get_areas_estadisticas_by_planta(
    planta_id: str,
    use_case: Annotated[GestionarPlantaEstructuraUseCase, Depends(get_planta_estructura_use_case)],
    claims: Annotated[dict, Depends(get_usuario_actual)],
):
    try:
        return use_case.obtener_areas_estadisticas(planta_id=planta_id, organizacion_id=_resolver_org_id(claims))
    except Exception as e:
        manejar_error_http(e)
