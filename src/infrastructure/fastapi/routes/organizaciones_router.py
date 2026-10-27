"""src/infrastructure/fastapi/routes/organizaciones_router.py."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.application.dtos.organizacion_dto import (
    OrganizacionResponseDTO,
    PlantaResponseDTO,
)
from src.application.use_cases.gestionar_acceso_plantas import GestionarAccesoPlantasUseCase
from src.application.use_cases.gestionar_dispositivos import GestionarDispositivosUseCase
from src.infrastructure.fastapi.auth_dependencies import get_acceso_plantas_use_case
from src.infrastructure.fastapi.dependencies import (
    get_dispositivos_use_case,
    get_usuario_actual,
)

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
    if rol == "superadmin":
        return orgs
    claim_org = claims.get("org")
    if claim_org is None:
        return []
    return [o for o in orgs if o.id == claim_org]


@router.get("/plantas", response_model=list[PlantaResponseDTO])
def list_plantas(
    use_case: Annotated[GestionarDispositivosUseCase, Depends(get_dispositivos_use_case)],
    claims: Annotated[dict, Depends(get_usuario_actual)],
    acceso_plantas: Annotated[GestionarAccesoPlantasUseCase, Depends(get_acceso_plantas_use_case)],
    organizacion_id: str | None = None,
):
    rol = claims.get("rol")
    if rol == "superadmin":
        target_org = organizacion_id
    else:
        claim_org = claims.get("org")
        if claim_org is None:
            return []
        if organizacion_id and organizacion_id != claim_org:
            return []
        target_org = claim_org

    plantas = use_case.listar_plantas(target_org)
    if rol == "superadmin":
        return plantas

    permitidas = acceso_plantas.resolver(claims.get("sub"), str(rol or ""), target_org)
    ids_permitidos = {p.id for p in permitidas}
    return [p for p in plantas if p.id in ids_permitidos]
