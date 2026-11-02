"""tests/unit/test_baja_usuario_sesiones.py — Issue datamaq#127: dar de baja a un usuario corta sus sesiones vivas.

`DELETE /api/v1/usuarios/{id}` solo ponía `esta_activo = False` y `get_usuario_actual` no miraba ese campo: un usuario
dado de baja conservaba el acceso hasta que vencía su token. Se prueba con `get_usuario_actual` y el handler REALES
y un repositorio de usuarios en memoria. Ids únicos por prueba: el servicio de revocación en memoria es global.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from src.domain.auth.entities import UsuarioAuth
from src.domain.auth.ports import RepositorioUsuariosPort
from src.infrastructure.auth.jwt_token_service import JwtTokenService
from src.infrastructure.fastapi.dependencies import get_usuario_actual
from src.infrastructure.fastapi.routes.usuarios_router import dar_baja_usuario
from src.infrastructure.settings.config import get_settings


class _RepoUsuarios(RepositorioUsuariosPort):
    def __init__(self, usuarios: list[UsuarioAuth]) -> None:
        self.usuarios = {u.id: u for u in usuarios}

    def obtener_por_usuario(self, usuario: str) -> UsuarioAuth | None:
        return next((u for u in self.usuarios.values() if u.usuario == usuario), None)

    def obtener_por_id(self, usuario_id: str) -> UsuarioAuth | None:
        return self.usuarios.get(usuario_id)

    def guardar(self, usuario: UsuarioAuth) -> UsuarioAuth:
        self.usuarios[usuario.id] = usuario
        return usuario


def _usuario(id_: str, org: str = "org-a") -> UsuarioAuth:
    return UsuarioAuth(id=id_, usuario=f"{id_}@planta.local", hash_contrasena="x", rol="operador", organizacion_id=org)


def _token(u: UsuarioAuth) -> str:
    vence = datetime.now(timezone.utc) + timedelta(hours=1)
    return JwtTokenService(get_settings().API_SECRET_KEY).generar(
        u.id, u.usuario, vence, rol=u.rol, organizacion_id=u.organizacion_id
    )


def _autenticar(repo: _RepoUsuarios, token: str) -> dict:
    return get_usuario_actual(authorization=f"Bearer {token}", datamaq_token=None, repo_usuarios=repo)


def _dar_de_baja(repo: _RepoUsuarios, usuario_id: str) -> None:
    admin = {"sub": "admin-baja", "usuario": "admin@planta.local", "rol": "admin", "org": "org-a"}
    dar_baja_usuario(usuario_id=usuario_id, claims=admin, repo_usuarios=repo, audit_use_case=None)


def test_el_token_vigente_de_un_usuario_dado_de_baja_deja_de_servir():
    ana = _usuario("u-baja-ana")
    repo = _RepoUsuarios([ana])
    token = _token(ana)
    assert _autenticar(repo, token)["sub"] == ana.id  # antes de la baja, funciona

    _dar_de_baja(repo, ana.id)

    with pytest.raises(HTTPException) as exc:
        _autenticar(repo, token)
    assert exc.value.status_code == 401


def test_la_baja_revoca_las_sesiones_anteriores_en_la_base():
    ana = _usuario("u-baja-rev")
    repo = _RepoUsuarios([ana])

    _dar_de_baja(repo, ana.id)

    guardada = repo.usuarios[ana.id]
    assert guardada.esta_activo is False
    assert guardada.sesiones_revocadas_antes_de is not None


def test_un_usuario_inactivo_no_pasa_aunque_su_token_sea_posterior_a_cualquier_revocacion():
    """Defensa en profundidad: un token nuevo (p. ej. emitido por un refresh OAuth) tampoco sirve si la cuenta está inactiva."""
    ana = _usuario("u-baja-inactiva")
    ana.esta_activo = False
    repo = _RepoUsuarios([ana])

    with pytest.raises(HTTPException) as exc:
        _autenticar(repo, _token(ana))
    assert exc.value.status_code == 401


def test_la_baja_de_un_usuario_no_afecta_a_los_demas():
    ana, beto = _usuario("u-baja-x"), _usuario("u-baja-y")
    repo = _RepoUsuarios([ana, beto])
    token_beto = _token(beto)

    _dar_de_baja(repo, ana.id)

    assert _autenticar(repo, token_beto)["sub"] == beto.id


def test_un_usuario_activo_sin_revocaciones_sigue_autenticando():
    ana = _usuario("u-baja-activa")
    repo = _RepoUsuarios([ana])

    assert _autenticar(repo, _token(ana))["sub"] == ana.id
