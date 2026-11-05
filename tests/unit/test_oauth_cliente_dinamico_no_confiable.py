"""tests/unit/test_oauth_cliente_dinamico_no_confiable.py — Issue datamaq#131: un alta dinámica no queda como confiable.

Un cliente registrado anónimamente (`dyn-<uuid>`) no puede quedar con `is_trusted=True`: esa marca la hereda el cliente
de Claude sembrado por defecto, y un alta de un tercero no debe compartirla. Las siembras de predeterminados sí mantienen
`is_trusted=True`. Repositorio OAuth real sobre SQLite en memoria.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.infrastructure.sqlalchemy.models import Base, OAuthClientModel
from src.infrastructure.sqlalchemy.repositories.oauth_repository import MySQLOAuthRepository


@pytest.fixture()
def db() -> Iterator[Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def test_alta_dinamica_queda_con_is_trusted_false(db: Session) -> None:
    repo = MySQLOAuthRepository(db)

    repo.registrar_o_actualizar_cliente(
        client_id="dyn-abc123def456",
        client_name="Cliente Dinámico",
        redirect_uris=["https://external.example/cb"],
    )

    fila = db.query(OAuthClientModel).filter(OAuthClientModel.client_id == "dyn-abc123def456").one()
    assert fila.is_trusted is False


def test_siembra_de_claude_sigue_confiable(db: Session) -> None:
    repo = MySQLOAuthRepository(db)

    repo.registrar_o_actualizar_cliente(
        client_id="claude-ai",
        client_name="Claude (Anthropic)",
        redirect_uris=["https://claude.ai/api/mcp/oauth_callback"],
    )

    fila = db.query(OAuthClientModel).filter(OAuthClientModel.client_id == "claude-ai").one()
    assert fila.is_trusted is True
