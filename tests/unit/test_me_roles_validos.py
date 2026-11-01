"""Issue #121: /auth/me debe responder a todo rol que ROLES_VALIDOS admite (incluido solo_lectura).

Antes, MeResponseDTO.rol era un Literal sin solo_lectura: un token válido con ese rol
hacía fallar la validación del DTO y /auth/me no respondía 200.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.application.use_cases.autenticar_usuario import ROLES_VALIDOS, AutenticarUsuarioUseCase
from src.domain.auth.entities import UsuarioAuth
from src.domain.auth.ports import RepositorioUsuariosPort
from src.domain.auth.services import HashContrasenaService
from src.infrastructure.fastapi.auth_dependencies import get_auth_use_case
from src.infrastructure.fastapi.dependencies import get_usuario_actual, get_usuarios_repository
from src.infrastructure.fastapi.server import create_app


class _RepoUsuariosEnMemoria(RepositorioUsuariosPort):
    def __init__(self, usuarios: list[UsuarioAuth]):
        self.usuarios = {u.id: u for u in usuarios}

    def obtener_por_usuario(self, usuario: str) -> UsuarioAuth | None:
        return next((u for u in self.usuarios.values() if u.usuario == usuario), None)

    def obtener_por_id(self, id_: str) -> UsuarioAuth | None:
        return self.usuarios.get(id_)

    def guardar(self, usuario: UsuarioAuth) -> None:
        self.usuarios[usuario.id] = usuario


def _caso_de_uso(repo: RepositorioUsuariosPort) -> AutenticarUsuarioUseCase:
    return AutenticarUsuarioUseCase(repo, HashContrasenaService(), MagicMock(), 480)


@pytest.mark.parametrize("rol", sorted(ROLES_VALIDOS))
def test_me_caso_de_uso_acepta_todo_rol_valido(rol: str):
    dto = _caso_de_uso(_RepoUsuariosEnMemoria([])).me({"usuario": "u1", "rol": rol})
    assert dto.rol == rol


@pytest.mark.parametrize("rol", sorted(ROLES_VALIDOS))
def test_me_ruta_responde_200_para_todo_rol_valido(rol: str):
    repo = _RepoUsuariosEnMemoria([])
    app = create_app()
    app.dependency_overrides[get_usuarios_repository] = lambda: repo
    app.dependency_overrides[get_auth_use_case] = lambda: _caso_de_uso(repo)
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "u-1", "usuario": "u1", "rol": rol}

    response = TestClient(app).get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["rol"] == rol


def test_me_ruta_solo_lectura_responde_200():
    """Caso reportado: un usuario solo_lectura no puede cargar su sesión."""
    repo = _RepoUsuariosEnMemoria([])
    app = create_app()
    app.dependency_overrides[get_usuarios_repository] = lambda: repo
    app.dependency_overrides[get_auth_use_case] = lambda: _caso_de_uso(repo)
    app.dependency_overrides[get_usuario_actual] = lambda: {
        "sub": "u-9",
        "usuario": "lectura@planta.local",
        "rol": "solo_lectura",
    }

    response = TestClient(app).get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["rol"] == "solo_lectura"
