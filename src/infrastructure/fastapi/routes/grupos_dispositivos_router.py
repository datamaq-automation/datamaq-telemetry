from typing import Annotated

from fastapi import APIRouter, Depends

from src.application.dtos.grupo_dispositivos_dto import (
    AgregarMiembroGrupoDTO,
    GrupoDispositivosCreateDTO,
    GrupoDispositivosResponseDTO,
    PuntoPotenciaGrupoDTO,
    ResumenGrupoDispositivosDTO,
)
from src.application.use_cases.consultar_grupo_dispositivos import ConsultarGrupoDispositivosUseCase
from src.application.use_cases.gestionar_grupos_dispositivos import GestionarGruposDispositivosUseCase
from src.infrastructure.fastapi.dependencies import (
    get_consultar_grupo_dispositivos_use_case,
    get_grupos_dispositivos_use_case,
    get_usuario_actual,
    requiere_rol_escritura,
)
from src.infrastructure.fastapi.device_ownership import verificar_propiedad_grupo_dispositivos
from src.infrastructure.fastapi.error_handler import manejar_error_http

router = APIRouter(
    prefix="/api/v1/grupos-dispositivos",
    tags=["Grupos de Dispositivos"],
    dependencies=[Depends(get_usuario_actual)],
)


@router.post("", response_model=GrupoDispositivosResponseDTO, dependencies=[Depends(requiere_rol_escritura)])
def crear_grupo(
    dto: GrupoDispositivosCreateDTO,
    use_case: Annotated[GestionarGruposDispositivosUseCase, Depends(get_grupos_dispositivos_use_case)],
):
    try:
        return use_case.crear_grupo(dto)
    except Exception as e:
        manejar_error_http(e)


@router.get("", response_model=list[GrupoDispositivosResponseDTO])
def listar_grupos(
    use_case: Annotated[GestionarGruposDispositivosUseCase, Depends(get_grupos_dispositivos_use_case)],
    planta_id: str,
):
    return use_case.listar_grupos(planta_id)


@router.get(
    "/{grupo_id}",
    response_model=GrupoDispositivosResponseDTO,
    dependencies=[Depends(verificar_propiedad_grupo_dispositivos)],
)
def obtener_grupo(
    grupo_id: str,
    use_case: Annotated[GestionarGruposDispositivosUseCase, Depends(get_grupos_dispositivos_use_case)],
):
    try:
        return use_case.obtener_grupo(grupo_id)
    except Exception as e:
        manejar_error_http(e)


@router.patch(
    "/{grupo_id}/miembros",
    response_model=GrupoDispositivosResponseDTO,
    dependencies=[Depends(requiere_rol_escritura), Depends(verificar_propiedad_grupo_dispositivos)],
)
def agregar_miembro(
    grupo_id: str,
    dto: AgregarMiembroGrupoDTO,
    use_case: Annotated[GestionarGruposDispositivosUseCase, Depends(get_grupos_dispositivos_use_case)],
):
    try:
        return use_case.agregar_miembro(grupo_id, dto.dispositivo_id)
    except Exception as e:
        manejar_error_http(e)


@router.delete(
    "/{grupo_id}/miembros/{dispositivo_id}",
    response_model=GrupoDispositivosResponseDTO,
    dependencies=[Depends(requiere_rol_escritura), Depends(verificar_propiedad_grupo_dispositivos)],
)
def quitar_miembro(
    grupo_id: str,
    dispositivo_id: str,
    use_case: Annotated[GestionarGruposDispositivosUseCase, Depends(get_grupos_dispositivos_use_case)],
):
    try:
        return use_case.quitar_miembro(grupo_id, dispositivo_id)
    except Exception as e:
        manejar_error_http(e)


@router.delete(
    "/{grupo_id}",
    dependencies=[Depends(requiere_rol_escritura), Depends(verificar_propiedad_grupo_dispositivos)],
)
def eliminar_grupo(
    grupo_id: str,
    use_case: Annotated[GestionarGruposDispositivosUseCase, Depends(get_grupos_dispositivos_use_case)],
):
    try:
        use_case.eliminar_grupo(grupo_id)
        return {"detail": "grupo_eliminado"}
    except Exception as e:
        manejar_error_http(e)


@router.get(
    "/{grupo_id}/resumen",
    response_model=ResumenGrupoDispositivosDTO,
    dependencies=[Depends(verificar_propiedad_grupo_dispositivos)],
)
def resumen_grupo(
    grupo_id: str,
    use_case: Annotated[ConsultarGrupoDispositivosUseCase, Depends(get_consultar_grupo_dispositivos_use_case)],
    granularity: str = "day",
    timezone: str = "America/Argentina/Buenos_Aires",
    dias: int | None = None,
):
    try:
        return use_case.resumen(grupo_id, granularity, timezone, dias)
    except Exception as e:
        manejar_error_http(e)


@router.get(
    "/{grupo_id}/resumen/historico",
    response_model=list[PuntoPotenciaGrupoDTO],
    dependencies=[Depends(verificar_propiedad_grupo_dispositivos)],
)
def historico_grupo(
    grupo_id: str,
    use_case: Annotated[ConsultarGrupoDispositivosUseCase, Depends(get_consultar_grupo_dispositivos_use_case)],
    hours: int = 24,
    granularity: str = "5m",
):
    try:
        return use_case.historico(grupo_id, granularity, hours)
    except Exception as e:
        manejar_error_http(e)
