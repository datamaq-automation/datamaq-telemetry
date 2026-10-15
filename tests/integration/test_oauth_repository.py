"""tests/integration/test_oauth_repository.py — Repositorio OAuth sobre SQLite: integración activa por usuario y cliente."""

import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.domain.oauth.entities import OAuthRefreshToken
from src.infrastructure.sqlalchemy.models import Base, UserModel
from src.infrastructure.sqlalchemy.repositories.oauth_repository import (
    MySQLOAuthRepository,
    sembrar_clientes_oauth,
)

CLIENT_ID = "claude-ai"


@pytest.fixture()
def repo_y_usuario() -> Iterator[tuple[MySQLOAuthRepository, str, Session]]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        sembrar_clientes_oauth(db)
        user_id = str(uuid.uuid4())
        db.add(
            UserModel(
                id=user_id,
                username=f"repo_{user_id[:8]}@datamaq.com",
                password_hash="hash",
                role="ingeniero",
                organization_id=None,
                is_active=True,
            )
        )
        db.commit()
        yield MySQLOAuthRepository(db), user_id, db


def _refresh(user_id: str, token_hash: str, *, expira_en: timedelta = timedelta(days=30)) -> OAuthRefreshToken:
    ahora = datetime.now(timezone.utc)
    return OAuthRefreshToken(
        token_hash=token_hash,
        client_id=CLIENT_ID,
        user_id=user_id,
        organization_id=None,
        scope="read:telemetria",
        expires_at=ahora + expira_en,
        revoked_at=None,
        created_at=ahora,
    )


def test_sin_refresh_tokens_no_hay_integracion_activa(repo_y_usuario):
    repo, user_id, _ = repo_y_usuario
    assert repo.tiene_integracion_activa(user_id, CLIENT_ID) is False


def test_refresh_sin_revocar_es_integracion_activa(repo_y_usuario):
    repo, user_id, _ = repo_y_usuario
    repo.guardar_refresh_token(_refresh(user_id, "h1"))
    assert repo.tiene_integracion_activa(user_id, CLIENT_ID) is True
    # Es por usuario y por cliente: otro cliente u otro usuario no heredan la integración.
    assert repo.tiene_integracion_activa(user_id, "otro-cliente") is False
    assert repo.tiene_integracion_activa(str(uuid.uuid4()), CLIENT_ID) is False


def test_revocar_por_cliente_apaga_la_integracion(repo_y_usuario):
    repo, user_id, _ = repo_y_usuario
    repo.guardar_refresh_token(_refresh(user_id, "h1"))
    repo.guardar_refresh_token(_refresh(user_id, "h2"))
    repo.revocar_tokens_usuario_cliente(user_id, CLIENT_ID, datetime.now(timezone.utc))
    assert repo.tiene_integracion_activa(user_id, CLIENT_ID) is False


def test_refresh_vencido_sin_revocar_cuenta_como_activo(repo_y_usuario):
    """Decisión (Issue #33): solo importa revoked_at; el vencimiento lo resuelve el exp del access token."""
    repo, user_id, _ = repo_y_usuario
    repo.guardar_refresh_token(_refresh(user_id, "h1", expira_en=timedelta(hours=-1)))
    assert repo.tiene_integracion_activa(user_id, CLIENT_ID) is True
