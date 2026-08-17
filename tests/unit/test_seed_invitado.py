"""Seed de usuario invitado (rol invitado) y login con claim de rol."""

from datetime import datetime

from scripts.seed_invitado import (
    CONTRASENA_DEFAULT,
    USUARIO_INVITADO,
    crear_invitado,
    obtener_contrasena,
)
from src.application.dtos.auth_dto import LoginRequestDTO
from src.application.use_cases.autenticar_usuario import AutenticarUsuarioUseCase
from src.domain.auth.entities import UsuarioAuth
from src.domain.auth.ports import GeneradorTokenPort, RepositorioUsuariosPort
from src.domain.auth.services import HashContrasenaService


class MockRepositorioUsuarios(RepositorioUsuariosPort):
    def __init__(self):
        self.usuarios: list[UsuarioAuth] = []

    def obtener_por_usuario(self, usuario: str) -> UsuarioAuth | None:
        for u in self.usuarios:
            if u.usuario == usuario:
                return u
        return None

    def guardar(self, usuario: UsuarioAuth) -> UsuarioAuth:
        self.usuarios.append(usuario)
        return usuario


class TokenServiceCapturaRol(GeneradorTokenPort):
    def __init__(self):
        self.rol = None

    def generar(self, usuario_id: str, usuario: str, expira_en: datetime, rol: str = "operador") -> str:
        self.rol = rol
        return f"token-{usuario_id}-{rol}"

    def verificar(self, token: str) -> dict | None:
        return None


def test_obtener_contrasena_respeta_env(capsys):
    contrasena = obtener_contrasena({"GUEST_PASSWORD": "clave-invitado-123"})
    assert contrasena == "clave-invitado-123"
    assert "ADVERTENCIA" not in capsys.readouterr().err


def test_obtener_contrasena_default_invitado_con_warning(capsys):
    contrasena = obtener_contrasena({})
    assert contrasena == CONTRASENA_DEFAULT
    assert "ADVERTENCIA" in capsys.readouterr().err


def test_crear_invitado_rol_y_hash():
    repo = MockRepositorioUsuarios()
    hash_service = HashContrasenaService()

    usuario = crear_invitado(repo, hash_service, "invitado")

    assert usuario.usuario == USUARIO_INVITADO
    assert usuario.rol == "invitado"
    assert usuario.esta_activo is True
    assert usuario.hash_contrasena.startswith("scrypt$")
    assert "invitado" not in usuario.hash_contrasena


def test_crear_invitado_idempotente():
    repo = MockRepositorioUsuarios()
    hash_service = HashContrasenaService()

    primero = crear_invitado(repo, hash_service, "invitado")
    segundo = crear_invitado(repo, hash_service, "invitado")

    assert len(repo.usuarios) == 1
    assert primero.id == segundo.id
    assert primero.hash_contrasena == segundo.hash_contrasena


def test_login_invitado_token_rol_invitado():
    repo = MockRepositorioUsuarios()
    hash_service = HashContrasenaService()
    crear_invitado(repo, hash_service, "invitado")

    token_service = TokenServiceCapturaRol()
    use_case = AutenticarUsuarioUseCase(repo, hash_service, token_service, 480)

    response = use_case.login(LoginRequestDTO(usuario=USUARIO_INVITADO, contrasena="invitado"))

    assert response.token.endswith("-invitado")
    assert token_service.rol == "invitado"
