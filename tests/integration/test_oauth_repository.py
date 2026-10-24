"""tests/integration/test_oauth_repository.py — Contrato de tiene_integracion_activa: doble en memoria y SQLAlchemy.

El mismo conjunto de casos corre contra las dos implementaciones del puerto, para que el doble de los tests
unitarios no se desvíe del repositorio real (Issue #33).
"""

import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.domain.oauth.entities import OAuthRefreshToken
from src.domain.oauth.ports import OAuthRepositoryPort
from src.infrastructure.sqlalchemy.models import Base, UserModel
from src.infrastructure.sqlalchemy.repositories.oauth_repository import (
    MySQLOAuthRepository,
    sembrar_clientes_oauth,
)
from tests.unit.test_oauth_use_cases import InMemoryOAuthRepository

CLIENT_ID = "claude-ai"
AHORA = datetime.now(timezone.utc)


@pytest.fixture(params=["inmemory", "sqlalchemy"])
def repo_y_usuario(request: pytest.FixtureRequest) -> Iterator[tuple[OAuthRepositoryPort, str]]:
    if request.param == "inmemory":
        yield InMemoryOAuthRepository(), str(uuid.uuid4())
        return
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
        yield MySQLOAuthRepository(db), user_id


def _guardar(
    repo: OAuthRepositoryPort,
    user_id: str,
    token_hash: str,
    *,
    creado: datetime = AHORA,
    vence: timedelta = timedelta(days=30),
    client_id: str = CLIENT_ID,
) -> None:
    repo.guardar_refresh_token(
        OAuthRefreshToken(
            token_hash=token_hash,
            client_id=client_id,
            user_id=user_id,
            organization_id=None,
            scope="read:telemetria",
            expires_at=creado + vence,
            revoked_at=None,
            created_at=creado,
        )
    )


def test_vacio_no_hay_integracion_activa(repo_y_usuario):
    repo, user_id = repo_y_usuario
    assert repo.tiene_integracion_activa(user_id, CLIENT_ID) is False


def test_refresh_sin_revocar_es_integracion_activa(repo_y_usuario):
    repo, user_id = repo_y_usuario
    _guardar(repo, user_id, "h1")
    assert repo.tiene_integracion_activa(user_id, CLIENT_ID) is True


def test_otro_cliente_no_hereda_la_integracion(repo_y_usuario):
    repo, user_id = repo_y_usuario
    _guardar(repo, user_id, "h1")
    assert repo.tiene_integracion_activa(user_id, "datamaq-mcp-client") is False


def test_otro_usuario_no_hereda_la_integracion(repo_y_usuario):
    repo, user_id = repo_y_usuario
    _guardar(repo, user_id, "h1")
    assert repo.tiene_integracion_activa(str(uuid.uuid4()), CLIENT_ID) is False


def test_revocado_no_cuenta(repo_y_usuario):
    repo, user_id = repo_y_usuario
    _guardar(repo, user_id, "h1")
    _guardar(repo, user_id, "h2")
    repo.revocar_tokens_usuario_cliente(user_id, CLIENT_ID, datetime.now(timezone.utc))
    assert repo.tiene_integracion_activa(user_id, CLIENT_ID) is False


def test_vencido_sin_revocar_cuenta_como_activo(repo_y_usuario):
    """Decisión (Issue #33): solo importa revoked_at; el vencimiento lo resuelve el exp del access token."""
    repo, user_id = repo_y_usuario
    _guardar(repo, user_id, "h1", vence=timedelta(hours=-1))
    assert repo.tiene_integracion_activa(user_id, CLIENT_ID) is True


def test_refresh_creado_despues_del_limite_no_cuenta(repo_y_usuario):
    """Reconexión: el refresh nuevo es posterior al access token viejo, así que no lo habilita."""
    repo, user_id = repo_y_usuario
    _guardar(repo, user_id, "h-nuevo", creado=AHORA)
    assert repo.tiene_integracion_activa(user_id, CLIENT_ID, AHORA - timedelta(hours=1)) is False


def test_refresh_creado_hasta_el_limite_cuenta(repo_y_usuario):
    repo, user_id = repo_y_usuario
    _guardar(repo, user_id, "h-viejo", creado=AHORA - timedelta(hours=1))
    assert repo.tiene_integracion_activa(user_id, CLIENT_ID, AHORA) is True
    # El límite es inclusivo.
    assert repo.tiene_integracion_activa(user_id, CLIENT_ID, AHORA - timedelta(hours=1)) is True
