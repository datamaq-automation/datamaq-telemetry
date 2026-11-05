"""src/infrastructure/fastapi/routes/alertas_router.py."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query

from src.application.dtos.alerta_dto import AlertaResolverRequestDTO, AlertaResponseDTO
from src.application.use_cases.gestionar_acceso_plantas import GestionarAccesoPlantasUseCase
from src.application.use_cases.gestionar_alertas import GestionarAlertasUseCase
from src.domain.auth.services import roles_de_acceso_global
from src.domain.telemetria.ports import RepositorioDispositivosPort
from src.infrastructure.fastapi.auth_dependencies import get_acceso_plantas_use_case
from src.infrastructure.fastapi.dependencies import (
    get_alertas_use_case,
    get_dispositivos_repository,
    get_usuario_actual,
    requiere_rol_escritura,
)
from src.infrastructure.fastapi.device_ownership import verificar_propiedad_alerta
from src.infrastructure.fastapi.error_handler import manejar_error_http
from src.infrastructure.fastapi.planta_ownership import resolver_planta_permitida
from src.infrastructure.settings.config import get_settings

router = APIRouter(
    prefix="/api/v1/alertas",
    tags=["Alertas"],
    dependencies=[Depends(get_usuario_actual)],
)


@router.get("", response_model=list[AlertaResponseDTO])
def list_alertas(
    use_case: Annotated[GestionarAlertasUseCase, Depends(get_alertas_use_case)],
    claims: Annotated[dict, Depends(get_usuario_actual)],
    acceso_plantas: Annotated[GestionarAccesoPlantasUseCase, Depends(get_acceso_plantas_use_case)],
    repo_dispositivos: Annotated[RepositorioDispositivosPort, Depends(get_dispositivos_repository)],
    device_id: str | None = Query(None, description="Filtrar por UUID de dispositivo"),
    solo_abiertas: bool = Query(False, description="Filtrar solo alertas no resueltas"),
    severidad: str | None = Query(None, description="Filtrar por severidad (INFO, WARNING, CRITICAL)"),
    limit: int = Query(100, le=500, description="Límite de registros"),
    desde: datetime | None = Query(None, description="Fecha de inicio ISO8601"),
    hasta: datetime | None = Query(None, description="Fecha de fin ISO8601"),
    planta_id: str | None = Query(None, description="Filtrar alertas por ID de planta"),
):
    if planta_id is not None:
        resolver_planta_permitida(claims=claims, acceso_plantas=acceso_plantas, planta_id=planta_id)

    # Roles globales ven todas; el resto, solo las de su organización (un device_id ajeno da []).
    rol = claims.get("rol")
    es_global = rol in roles_de_acceso_global(get_settings().ROLES_ACCESO_GLOBAL_EXTRA)
    organizacion_id = None
    if not es_global:
        organizacion_id = claims.get("org")
        if not organizacion_id:
            return []  # Sin organización asignada: fail-closed, como GET /dispositivos.

    plantas_usuario = claims.get("plantas")
    plantas_permitidas: set[str] | None = None
    if not es_global and plantas_usuario is not None:
        plantas_permitidas = set(plantas_usuario)
        if device_id is not None:
            dev = repo_dispositivos.obtener_por_id(device_id)
            if dev is None:
                try:
                    from src.domain.telemetria.servicios.identificador_medidor import (
                        parsear_identificador_medidor,
                    )

                    ident = parsear_identificador_medidor(device_id)
                    dev = repo_dispositivos.obtener_por_uid(ident.mac, ident.medidor_id)
                except Exception:
                    dev = None
            if dev is None or dev.planta_id not in plantas_permitidas:
                return []

    alertas = use_case.listar_alertas(
        dispositivo_id=device_id,
        solo_abiertas=solo_abiertas,
        severidad=severidad,
        limite=limit,
        desde=desde,
        hasta=hasta,
        organizacion_id=organizacion_id,
        planta_id=planta_id,
    )

    if plantas_permitidas is not None and planta_id is None:
        cache_dispositivos: dict[str, str | None] = {}
        alertas_filtradas: list[AlertaResponseDTO] = []
        for a in alertas:
            if a.dispositivo_id not in cache_dispositivos:
                d = repo_dispositivos.obtener_por_id(a.dispositivo_id)
                cache_dispositivos[a.dispositivo_id] = d.planta_id if d else None
            if cache_dispositivos[a.dispositivo_id] in plantas_permitidas:
                alertas_filtradas.append(a)
        return alertas_filtradas

    return alertas


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
