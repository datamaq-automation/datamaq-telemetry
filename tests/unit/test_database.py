"""Pruebas de la configuración de base de datos (database.py)."""

from sqlalchemy import create_engine

from src.infrastructure.sqlalchemy import database as database_mod
from src.infrastructure.sqlalchemy.database import (
    create_tables_if_needed,
    get_db_session,
    get_engine,
    get_session_factory,
)


def test_get_engine_cacheado():
    get_engine.cache_clear()

    engine = get_engine()

    assert engine is not None
    assert get_engine() is engine


def test_get_session_factory():
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    factory = get_session_factory()

    assert factory is not None


def test_get_db_session():
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    generador = get_db_session()
    db = next(generador)

    assert db is not None
    generador.close()


def test_create_tables_if_needed_success(monkeypatch):
    engine = create_engine("sqlite://")
    monkeypatch.setattr(database_mod, "get_engine", lambda: engine)

    create_tables_if_needed()


def test_create_tables_if_needed_error(monkeypatch, capsys):
    def _boom():
        raise RuntimeError("sin conexion")

    monkeypatch.setattr(database_mod, "get_engine", _boom)

    create_tables_if_needed()

    assert "Could not auto-create" in capsys.readouterr().out
