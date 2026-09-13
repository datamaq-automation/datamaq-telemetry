"""src/infrastructure/fastapi/routes/usuarios_router.py — Router de administración de usuarios."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from src.application.dtos.auth_dto import AsignarPlantasRequestDTO, PlantaAccesoDTO
from src.application.use_cases.gestionar_acceso_plantas import GestionarAccesoPlantasUseCase
from src.domain.auth.entities import UsuarioAuth
from src.domain.auth.ports import RepositorioUsuariosPort
from src.domain.auth.services import HashContrasenaService
from src.infrastructure.fastapi.auth_dependencies import get_acceso_plantas_use_case
from src.infrastructure.fastapi.dependencies import (
    get_usuario_actual,
    get_usuarios_repository,
    requiere_rol_admin,
)
from src.infrastructure.fastapi.error_handler import manejar_error_http
from src.infrastructure.settings.config import get_settings


class CrearUsuarioRequestDTO(BaseModel):
    usuario: str = Field(..., min_length=3, max_length=50)
    rol: str = Field("operador", description="operador, admin, mantenimiento, ingeniero, etc.")
    organizacion_id: str | None = None


class UsuarioResponseDTO(BaseModel):
    id: str
    usuario: str
    rol: str
    organizacion_id: str | None
    esta_activo: bool
    model_config = ConfigDict(from_attributes=True)


router = APIRouter(prefix="/api/v1/usuarios", tags=["Administración de Usuarios"])


@router.post(
    "",
    response_model=UsuarioResponseDTO,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(requiere_rol_admin)],
)
def crear_usuario(
    dto: CrearUsuarioRequestDTO,
    claims: Annotated[dict, Depends(get_usuario_actual)],
    repo_usuarios: Annotated[RepositorioUsuariosPort, Depends(get_usuarios_repository)],
) -> UsuarioResponseDTO:
    existente = repo_usuarios.obtener_por_usuario(dto.usuario)
    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El nombre de usuario '{dto.usuario}' ya existe.",
        )

    target_org = dto.organizacion_id or claims.get("org")
    settings = get_settings()
    hash_pwd = HashContrasenaService.generar_hash(settings.DEFAULT_USER_PASSWORD)

    nuevo_usuario = UsuarioAuth(
        id=str(uuid.uuid4()),
        usuario=dto.usuario,
        hash_contrasena=hash_pwd,
        esta_activo=True,
        rol=dto.rol,
        organizacion_id=target_org,
    )

    guardado = repo_usuarios.guardar(nuevo_usuario)
    return UsuarioResponseDTO(
        id=guardado.id,
        usuario=guardado.usuario,
        rol=guardado.rol,
        organizacion_id=guardado.organizacion_id,
        esta_activo=guardado.esta_activo,
    )


def _verificar_misma_organizacion(claims: dict, usuario_id: str, repo_usuarios: RepositorioUsuariosPort) -> None:
    """Un admin solo administra usuarios de su propia organización; superadmin, cualquiera."""
    if claims.get("rol") == "superadmin":
        return
    usuario = repo_usuarios.obtener_por_id(usuario_id)
    if usuario is not None and usuario.organizacion_id != claims.get("org"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")


@router.get(
    "/{usuario_id}/plantas",
    response_model=list[PlantaAccesoDTO],
    dependencies=[Depends(requiere_rol_admin)],
)
def listar_plantas_usuario(
    usuario_id: str,
    claims: Annotated[dict, Depends(get_usuario_actual)],
    repo_usuarios: Annotated[RepositorioUsuariosPort, Depends(get_usuarios_repository)],
    use_case: Annotated[GestionarAccesoPlantasUseCase, Depends(get_acceso_plantas_use_case)],
) -> list[PlantaAccesoDTO]:
    _verificar_misma_organizacion(claims, usuario_id, repo_usuarios)
    try:
        return use_case.listar_asignadas(usuario_id)
    except Exception as e:
        manejar_error_http(e)


@router.put(
    "/{usuario_id}/plantas",
    response_model=list[PlantaAccesoDTO],
    dependencies=[Depends(requiere_rol_admin)],
)
def asignar_plantas_usuario(
    usuario_id: str,
    dto: AsignarPlantasRequestDTO,
    claims: Annotated[dict, Depends(get_usuario_actual)],
    repo_usuarios: Annotated[RepositorioUsuariosPort, Depends(get_usuarios_repository)],
    use_case: Annotated[GestionarAccesoPlantasUseCase, Depends(get_acceso_plantas_use_case)],
) -> list[PlantaAccesoDTO]:
    """Reemplaza el conjunto de plantas asignadas; lista vacía restaura el acceso por defecto a toda la org."""
    _verificar_misma_organizacion(claims, usuario_id, repo_usuarios)
    try:
        return use_case.asignar(usuario_id, dto)
    except Exception as e:
        manejar_error_http(e)
