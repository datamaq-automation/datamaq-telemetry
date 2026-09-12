"""src/infrastructure/fastapi/routes/organizaciones_router.py."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.application.dtos.organizacion_dto import (
    OrganizacionCreateDTO,
    OrganizacionResponseDTO,
    PlantaCreateDTO,
    PlantaResponseDTO,
)
from src.application.use_cases.gestionar_dispositivos import GestionarDispositivosUseCase
from src.infrastructure.fastapi.dependencies import (
    get_dispositivos_use_case,
    get_usuario_actual,
    requiere_rol_escritura,
)
from src.infrastructure.fastapi.error_handler import manejar_error_http

router = APIRouter(
    prefix="/api/v1",
    tags=["Organizaciones y Plantas"],
    dependencies=[Depends(get_usuario_actual)],
)


@router.get("/organizaciones", response_model=list[OrganizacionResponseDTO])
def list_organizaciones(
    use_case: Annotated[GestionarDispositivosUseCase, Depends(get_dispositivos_use_case)],
    claims: Annotated[dict, Depends(get_usuario_actual)],
):
    rol = claims.get("rol")
    orgs = use_case.listar_organizaciones()
    if rol in ("superadmin", "invitado_global"):
        return orgs
    claim_org = claims.get("org")
    if claim_org is None:
        return []
    return [o for o in orgs if o.id == claim_org]


@router.post("/organizaciones", response_model=OrganizacionResponseDTO, dependencies=[Depends(requiere_rol_escritura)])
def create_organizacion(
    dto: OrganizacionCreateDTO,
    use_case: Annotated[GestionarDispositivosUseCase, Depends(get_dispositivos_use_case)],
):
    try:
        return use_case.crear_organizacion(dto)
    except Exception as e:
        manejar_error_http(e)


@router.get("/plantas", response_model=list[PlantaResponseDTO])
def list_plantas(
    use_case: Annotated[GestionarDispositivosUseCase, Depends(get_dispositivos_use_case)],
    claims: Annotated[dict, Depends(get_usuario_actual)],
    organizacion_id: str | None = None,
):
    rol = claims.get("rol")
    if rol in ("superadmin", "invitado_global"):
        target_org = organizacion_id
    else:
        claim_org = claims.get("org")
        if claim_org is None:
            return []
        if organizacion_id and organizacion_id != claim_org:
            return []
        target_org = claim_org

    return use_case.listar_plantas(target_org)


@router.post("/plantas", response_model=PlantaResponseDTO, dependencies=[Depends(requiere_rol_escritura)])
def create_planta(
    dto: PlantaCreateDTO,
    use_case: Annotated[GestionarDispositivosUseCase, Depends(get_dispositivos_use_case)],
):
    try:
        return use_case.crear_planta(dto)
    except Exception as e:
        manejar_error_http(e)
