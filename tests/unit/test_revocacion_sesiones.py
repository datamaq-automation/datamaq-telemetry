"""tests/unit/test_revocacion_sesiones.py — Tests de revocación global de sesiones (ISO 27001 A.5.15)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, Response

from src.application.dtos.audit_dto import RegistrarAuditLogDTO
from src.domain.auth.entities import UsuarioAuth
from src.domain.auth.ports import RepositorioUsuariosPort
from src.infrastructure.auth.jwt_token_service import JwtTokenService
from src.infrastructure.fastapi.dependencies import (
    get_usuario_actual,
)
from src.infrastructure.fastapi.routes.auth_router import logout_todas as logout_todas_handler
from src.infrastructure.settings.config import get_settings


class MockRepoUsuarios(RepositorioUsuariosPort):
    def __init__(self, usuarios: list[UsuarioAuth]):
        self.usuarios = {u.id: u for u in usuarios}

    def obtener_por_usuario(self, usuario: str) -> UsuarioAuth | None:
        for u in self.usuarios.values():
            if u.usuario == usuario:
                return u
        return None

    def obtener_por_id(self, usuario_id: str) -> UsuarioAuth | None:
        return self.usuarios.get(usuario_id)

    def guardar(self, usuario: UsuarioAuth) -> UsuarioAuth:
        self.usuarios[usuario.id] = usuario
        return usuario


def test_logout_todas_actualiza_timestamp_y_cookie():
    ahora = datetime.now(timezone.utc)
    user = UsuarioAuth(
        id="user-123",
        usuario="operador@planta.local",
        hash_contrasena="hash",
        sesiones_revocadas_antes_de=None,
    )
    repo = MockRepoUsuarios([user])
    mock_audit = MagicMock()

    response = Response()
    claims = {"sub": "user-123", "usuario": "operador@planta.local", "rol": "operador"}

    resultado = logout_todas_handler(
        claims=claims,
        response=response,
        settings=get_settings(),
        repo_usuarios=repo,
        audit_use_case=mock_audit,
    )

    assert resultado == {"detail": "todas_las_sesiones_revocadas"}
    # Verifica que el usuario guardó el timestamp de revocación
    updated = repo.obtener_por_id("user-123")
    assert updated is not None
    assert updated.sesiones_revocadas_antes_de is not None
    assert updated.sesiones_revocadas_antes_de >= ahora

    # Cookie fue eliminada
    set_cookie = response.headers.get("set-cookie", "")
    assert "Max-Age=0" in set_cookie or "max-age=0" in set_cookie

    # Evento de auditoría fue emitido
    mock_audit.ejecutar.assert_called_once()
    dto_emitido: RegistrarAuditLogDTO = mock_audit.ejecutar.call_args[0][0]
    assert dto_emitido.categoria == "AUTH"
    assert dto_emitido.accion == "LOGOUT_TODAS_SESIONES"
    assert dto_emitido.resultado == "EXITO"
    assert dto_emitido.actor_usuario_id == "user-123"


def test_get_usuario_actual_invalida_token_emitido_antes_de_revocacion():
    settings = get_settings()
    token_service = JwtTokenService(settings.API_SECRET_KEY)

    ahora = datetime.now(timezone.utc)

    # Token con iat en ahora
    token = token_service.generar("user-123", "operador@planta.local", ahora + timedelta(hours=8))
    # Hack/Override iat al pasado para simular emisión antes de la revocación
    claims_raw = token_service.verificar(token)
    assert claims_raw is not None

    user = UsuarioAuth(
        id="user-123",
        usuario="operador@planta.local",
        hash_contrasena="hash",
        sesiones_revocadas_antes_de=ahora + timedelta(minutes=1),  # Revocado en el futuro respecto al iat
    )
    repo = MockRepoUsuarios([user])

    with pytest.raises(HTTPException) as exc_info:
        get_usuario_actual(
            authorization=f"Bearer {token}",
            datamaq_token=None,
            repo_usuarios=repo,
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "credenciales_invalidas"


def test_get_usuario_actual_permite_token_emitido_despues_de_revocacion():
    settings = get_settings()
    token_service = JwtTokenService(settings.API_SECRET_KEY)

    ahora = datetime.now(timezone.utc)
    # Sesiones revocadas hace 1 hora
    user = UsuarioAuth(
        id="user-123",
        usuario="operador@planta.local",
        hash_contrasena="hash",
        sesiones_revocadas_antes_de=ahora - timedelta(hours=1),
    )
    repo = MockRepoUsuarios([user])

    # Nuevo login emitido ahora (iat > sesiones_revocadas_antes_de)
    token = token_service.generar("user-123", "operador@planta.local", ahora + timedelta(hours=8))

    claims = get_usuario_actual(
        authorization=f"Bearer {token}",
        datamaq_token=None,
        repo_usuarios=repo,
    )

    assert claims["sub"] == "user-123"
