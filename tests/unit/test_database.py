"""tests/unit/test_database.py — Pruebas de la configuración de base de datos (database.py)."""

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

    assert "auto_create_tables_failed" in capsys.readouterr().out


def test_verificar_estado_migraciones_sincronizado(monkeypatch):
    from unittest.mock import MagicMock

    engine = create_engine("sqlite://")
    mock_context = MagicMock()
    mock_context.get_current_revision.return_value = "f6a7b8c9d0e1"
    mock_script = MagicMock()
    mock_script.get_current_head.return_value = "f6a7b8c9d0e1"

    monkeypatch.setattr(database_mod.MigrationContext, "configure", lambda conn: mock_context)
    monkeypatch.setattr(database_mod.ScriptDirectory, "from_config", lambda cfg: mock_script)

    resultado = database_mod.verificar_estado_migraciones(engine)
    assert resultado["sincronizado"] is True
    assert resultado["current_rev"] == "f6a7b8c9d0e1"
    assert resultado["head_rev"] == "f6a7b8c9d0e1"


def test_verificar_estado_migraciones_desfasaje(monkeypatch):
    from unittest.mock import MagicMock

    engine = create_engine("sqlite://")
    mock_context = MagicMock()
    mock_context.get_current_revision.return_value = "d4e5f6a7b8c9"
    mock_script = MagicMock()
    mock_script.get_current_head.return_value = "f6a7b8c9d0e1"

    monkeypatch.setattr(database_mod.MigrationContext, "configure", lambda conn: mock_context)
    monkeypatch.setattr(database_mod.ScriptDirectory, "from_config", lambda cfg: mock_script)

    resultado = database_mod.verificar_estado_migraciones(engine)
    assert resultado["sincronizado"] is False
    assert resultado["current_rev"] == "d4e5f6a7b8c9"
    assert resultado["head_rev"] == "f6a7b8c9d0e1"


def test_verificar_estado_migraciones_sin_alembic_ini(monkeypatch, tmp_path):
    from unittest.mock import MagicMock

    engine = create_engine("sqlite://")
    mock_context = MagicMock()
    mock_context.get_current_revision.return_value = "abc123"

    monkeypatch.setattr(database_mod.MigrationContext, "configure", lambda conn: mock_context)
    monkeypatch.setattr(database_mod.Path, "exists", lambda self: False)

    resultado = database_mod.verificar_estado_migraciones(engine)
    assert resultado["sincronizado"] is True
    assert resultado["detalle"] == "alembic_ini_no_encontrado"


def test_verificar_estado_migraciones_error_conexion(monkeypatch):
    def _boom():
        raise RuntimeError("db_down")

    monkeypatch.setattr(database_mod, "get_engine", _boom)

    resultado = database_mod.verificar_estado_migraciones()
    assert resultado["sincronizado"] is False
    assert "db_down" in resultado["error"]
