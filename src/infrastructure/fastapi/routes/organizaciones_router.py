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
):
    return use_case.listar_organizaciones()


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
    organizacion_id: str | None = None,
):
    return use_case.listar_plantas(organizacion_id)


@router.post("/plantas", response_model=PlantaResponseDTO, dependencies=[Depends(requiere_rol_escritura)])
def create_planta(
    dto: PlantaCreateDTO,
    use_case: Annotated[GestionarDispositivosUseCase, Depends(get_dispositivos_use_case)],
):
    try:
        return use_case.crear_planta(dto)
    except Exception as e:
        manejar_error_http(e)
