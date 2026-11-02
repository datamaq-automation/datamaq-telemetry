"""src/infrastructure/fastapi/routes/usuarios_router.py — Router de administración de usuarios."""

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from src.application.dtos.audit_dto import RegistrarAuditLogDTO
from src.application.dtos.auth_dto import AsignarPlantasRequestDTO, PlantaAccesoDTO
from src.application.use_cases.gestionar_acceso_plantas import GestionarAccesoPlantasUseCase
from src.application.use_cases.gestionar_auditoria import RegistrarEventoAuditoriaUseCase
from src.domain.auth.entities import UsuarioAuth
from src.domain.auth.ports import RepositorioUsuariosPort
from src.domain.auth.services import HashContrasenaService
from src.infrastructure.fastapi.auth_dependencies import get_acceso_plantas_use_case
from src.infrastructure.fastapi.dependencies import (
    get_registrar_auditoria_use_case,
    get_token_revocation_service,
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


class CambiarRolUsuarioDTO(BaseModel):
    rol: str = Field(..., min_length=2, max_length=50, description="Nuevo rol asignado")


class UsuarioResponseDTO(BaseModel):
    id: str
    usuario: str
    rol: str
    organizacion_id: str | None
    esta_activo: bool
    puede_cambiar_contrasena: bool = True
    fecha_ultimo_cambio: datetime | None = None
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
    audit_use_case: Annotated[RegistrarEventoAuditoriaUseCase | None, Depends(get_registrar_auditoria_use_case)] = None,
) -> UsuarioResponseDTO:
    _verificar_alta_permitida(dto, claims)
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

    if audit_use_case is not None:
        try:
            audit_use_case.ejecutar(
                RegistrarAuditLogDTO(
                    categoria="USUARIOS",
                    accion="ALTA",
                    resultado="EXITO",
                    actor_usuario_id=claims.get("sub"),
                    actor_email=claims.get("usuario"),
                    recurso_tipo="usuario",
                    recurso_id=guardado.id,
                    metadatos={
                        "usuario": guardado.usuario,
                        "rol": guardado.rol,
                        "organizacion_id": guardado.organizacion_id,
                    },
                )
            )
        except Exception:
            pass

    return UsuarioResponseDTO(
        id=guardado.id,
        usuario=guardado.usuario,
        rol=guardado.rol,
        organizacion_id=guardado.organizacion_id,
        esta_activo=guardado.esta_activo,
    )


@router.delete(
    "/{usuario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(requiere_rol_admin)],
)
def dar_baja_usuario(
    usuario_id: str,
    claims: Annotated[dict, Depends(get_usuario_actual)],
    repo_usuarios: Annotated[RepositorioUsuariosPort, Depends(get_usuarios_repository)],
    audit_use_case: Annotated[RegistrarEventoAuditoriaUseCase | None, Depends(get_registrar_auditoria_use_case)] = None,
):
    _verificar_misma_organizacion(claims, usuario_id, repo_usuarios)
    usuario = repo_usuarios.obtener_por_id(usuario_id)
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")

    _verificar_baja_permitida(claims, usuario)
    # La baja corta también las sesiones abiertas (datamaq#127), igual que «cerrar todas las sesiones».
    ahora = datetime.now(timezone.utc)
    usuario.esta_activo = False
    usuario.sesiones_revocadas_antes_de = ahora
    repo_usuarios.guardar(usuario)
    get_token_revocation_service().revocar_usuario(usuario.id, int(ahora.timestamp()))

    if audit_use_case is not None:
        try:
            audit_use_case.ejecutar(
                RegistrarAuditLogDTO(
                    categoria="USUARIOS",
                    accion="BAJA",
                    resultado="EXITO",
                    actor_usuario_id=claims.get("sub"),
                    actor_email=claims.get("usuario"),
                    recurso_tipo="usuario",
                    recurso_id=usuario_id,
                    metadatos={"usuario": usuario.usuario},
                )
            )
        except Exception:
            pass


@router.patch(
    "/{usuario_id}/rol",
    response_model=UsuarioResponseDTO,
    dependencies=[Depends(requiere_rol_admin)],
)
def cambiar_rol_usuario(
    usuario_id: str,
    dto: CambiarRolUsuarioDTO,
    claims: Annotated[dict, Depends(get_usuario_actual)],
    repo_usuarios: Annotated[RepositorioUsuariosPort, Depends(get_usuarios_repository)],
    audit_use_case: Annotated[RegistrarEventoAuditoriaUseCase | None, Depends(get_registrar_auditoria_use_case)] = None,
) -> UsuarioResponseDTO:
    _verificar_misma_organizacion(claims, usuario_id, repo_usuarios)
    usuario = repo_usuarios.obtener_por_id(usuario_id)
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")

    _verificar_cambio_de_rol_permitido(claims, usuario, dto.rol)
    anterior_rol = usuario.rol
    usuario.rol = dto.rol
    guardado = repo_usuarios.guardar(usuario)

    if audit_use_case is not None:
        try:
            audit_use_case.ejecutar(
                RegistrarAuditLogDTO(
                    categoria="USUARIOS",
                    accion="CAMBIO_ROL",
                    resultado="EXITO",
                    actor_usuario_id=claims.get("sub"),
                    actor_email=claims.get("usuario"),
                    recurso_tipo="usuario",
                    recurso_id=usuario_id,
                    metadatos={"rol_anterior": anterior_rol, "rol_nuevo": dto.rol},
                )
            )
        except Exception:
            pass

    return UsuarioResponseDTO(
        id=guardado.id,
        usuario=guardado.usuario,
        rol=guardado.rol,
        organizacion_id=guardado.organizacion_id,
        esta_activo=guardado.esta_activo,
    )


def _verificar_baja_permitida(claims: dict, usuario: UsuarioAuth) -> None:
    """Solo un superadmin da de baja a otro superadmin (#39, decisión del dueño)."""
    if claims.get("rol") != "superadmin" and usuario.rol == "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")


def _verificar_misma_organizacion(claims: dict, usuario_id: str, repo_usuarios: RepositorioUsuariosPort) -> None:
    """Un admin solo administra usuarios de su propia organización; superadmin, cualquiera."""
    if claims.get("rol") == "superadmin":
        return
    usuario = repo_usuarios.obtener_por_id(usuario_id)
    if usuario is not None and usuario.organizacion_id != claims.get("org"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")


def _verificar_alta_permitida(dto: CrearUsuarioRequestDTO, claims: dict) -> None:
    """Un admin crea usuarios solo en su organización y nunca con rol superadmin (#40)."""
    if claims.get("rol") == "superadmin":
        return
    if dto.rol == "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    if dto.organizacion_id is not None and dto.organizacion_id != claims.get("org"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")


def _verificar_cambio_de_rol_permitido(claims: dict, usuario: UsuarioAuth, rol_nuevo: str) -> None:
    """Un admin no asigna ni quita el rol superadmin (#40)."""
    if claims.get("rol") == "superadmin":
        return
    if usuario.rol == "superadmin" or rol_nuevo == "superadmin":
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
