"""Compatibilidad temporal de los roles invitado e invitado_global (TODO #65).

Un token emitido con un rol retirado no se trata como un usuario vigente: no pasa por el
caso de uso de /me y su respuesta no le concede ningún permiso (ni plantas, ni organización,
ni escritura, ni 2FA, ni acceso global). Solo devuelve el rol tal como está en el token para
que el frontend de main siga cargando la sesión.

TODO(#65): quitar cuando el frontend de main de app-datamaq deje de llamar a estos roles.
"""

from typing import Any

from src.application.dtos.auth_dto import MeResponseDTO
from src.domain.auth.ports import RepositorioUsuariosPort

# TODO(#65): quitar con los roles de compatibilidad.
ROLES_COMPAT_CLIENTE = frozenset({"invitado", "invitado_global"})


def es_rol_compat(rol: Any) -> bool:
    return rol in ROLES_COMPAT_CLIENTE


def construir_me_compat(claims: dict[str, Any], repo_usuarios: RepositorioUsuariosPort) -> dict[str, Any]:
    """Arma la respuesta de /me para un rol retirado, sin invocar el caso de uso."""
    usuario = str(claims.get("usuario") or claims.get("sub") or "anon")
    totp_enabled = False
    sub = str(claims.get("sub") or "")
    user = None
    if sub and sub != "anon":
        user = repo_usuarios.obtener_por_id(sub)
    if user is None and usuario != "anon":
        user = repo_usuarios.obtener_por_usuario(usuario)
    if user is not None:
        totp_enabled = bool(user.totp_enabled)
    # model_construct no valida: aquí el rol es el retirado, que el DTO ya no admite.
    dto = MeResponseDTO.model_construct(usuario=usuario, rol=claims["rol"], totp_enabled=totp_enabled, plantas=[])
    return dto.model_dump(mode="json")
