"""Pruebas de la infraestructura de migraciones Alembic (specs/migraciones.md)."""

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command

RAIZ = Path(__file__).resolve().parents[2]
ALEMBIC_INI = RAIZ / "alembic.ini"
ENV_PY = RAIZ / "alembic" / "env.py"
REVISION_INICIAL = "209ce0774d59"
REVISION_HEAD = "a1b2c3d4e5f6"

TABLAS_MODELO = {
    "plans",
    "organizations",
    "facilities",
    "devices",
    "telemetry_instantaneous",
    "telemetry_energy",
    "device_status_logs",
    "device_alerts",
    "users",
}


def _config() -> Config:
    """Config de Alembic apuntando al alembic.ini del repo (la URL la resuelve env.py)."""
    return Config(str(ALEMBIC_INI))


def _crear_esquema_legacy(engine) -> None:
    """Crea una BD legacy (sin role, plan_id, wifi_calidad ni índices) con datos de prueba."""
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE plans (id VARCHAR(36) PRIMARY KEY)"))
        conn.execute(
            text(
                "CREATE TABLE organizations ("
                "id VARCHAR(36) PRIMARY KEY, name VARCHAR(150) NOT NULL, "
                "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE users ("
                "id VARCHAR(36) PRIMARY KEY, username VARCHAR(150) NOT NULL UNIQUE, "
                "password_hash VARCHAR(255) NOT NULL, is_active BOOLEAN NOT NULL, "
                "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE telemetry_instantaneous ("
                "id INTEGER PRIMARY KEY, device_id VARCHAR(36), recorded_at DATETIME)"
            )
        )
        conn.execute(
            text("CREATE TABLE telemetry_energy (id INTEGER PRIMARY KEY, device_id VARCHAR(36), recorded_at DATETIME)")
        )
        conn.execute(
            text(
                "CREATE TABLE device_status_logs ("
                "id INTEGER PRIMARY KEY, device_id VARCHAR(36), recorded_at DATETIME, "
                "wifi_rssi_dbm INTEGER)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE device_alerts ("
                "id INTEGER PRIMARY KEY, device_id VARCHAR(36), is_resolved BOOLEAN, "
                "resolved_at DATETIME)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO users (id, username, password_hash, is_active, created_at, updated_at) "
                "VALUES ('u1', 'invitado', 'hash', 1, '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
            )
        )
        conn.execute(
            text("INSERT INTO device_status_logs (id, device_id, recorded_at) VALUES (1, 'd1', '2026-01-01 00:00:00')")
        )


def _cargar_env(monkeypatch) -> dict[str, str]:
    """Carga alembic/env.py con un contexto falso; retorna las opciones main seteadas."""
    opciones: dict[str, str] = {}

    def _set_opcion(clave: str, valor: str) -> None:
        opciones[clave] = valor

    config_falso = types.SimpleNamespace(
        config_file_name=None,
        config_ini_section="alembic",
        set_main_option=_set_opcion,
        get_main_option=lambda clave: opciones.get(clave),
    )

    contexto = types.SimpleNamespace(config=config_falso)
    contexto.is_offline_mode = lambda: True
    contexto.configure = MagicMock()
    contexto.run_migrations = MagicMock()
    contexto.begin_transaction = MagicMock()

    mod_alembic = types.ModuleType("alembic")
    mod_alembic.context = contexto
    monkeypatch.setitem(sys.modules, "alembic", mod_alembic)

    spec = importlib.util.spec_from_file_location("env_bajo_prueba", ENV_PY)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["env_bajo_prueba"] = modulo
    spec.loader.exec_module(modulo)

    return opciones


def test_env_usa_override_datatabase_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///override.db")

    opciones = _cargar_env(monkeypatch)

    assert opciones["sqlalchemy.url"] == "sqlite:///override.db"


def test_env_usa_settings_sin_override(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    class _SettingsFake:
        database_url = "sqlite:///desde_settings.db"

    monkeypatch.setattr("src.infrastructure.settings.config.get_settings", lambda: _SettingsFake())

    opciones = _cargar_env(monkeypatch)

    assert opciones["sqlalchemy.url"] == "sqlite:///desde_settings.db"


def test_upgrade_head_crea_esquema_completo(tmp_path, monkeypatch):
    db = tmp_path / "nueva.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    cfg = _config()

    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db}")
    tablas = set(inspect(engine).get_table_names())
    assert TABLAS_MODELO <= tablas
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert version == REVISION_HEAD


def test_reconcile_agrega_users_role_legacy(tmp_path, monkeypatch):
    db = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db}")
    _crear_esquema_legacy(engine)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    cfg = _config()

    command.stamp(cfg, REVISION_INICIAL)
    command.upgrade(cfg, "head")

    columnas = {c["name"] for c in inspect(engine).get_columns("users")}
    assert "role" in columnas
    with engine.connect() as conn:
        rol = conn.execute(text("SELECT role FROM users WHERE username = 'invitado'")).scalar()
    assert rol == "operador"


def test_reconcile_agrega_organizations_plan_id_legacy(tmp_path, monkeypatch):
    db = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db}")
    _crear_esquema_legacy(engine)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    cfg = _config()

    command.stamp(cfg, REVISION_INICIAL)
    command.upgrade(cfg, "head")

    columnas = {c["name"] for c in inspect(engine).get_columns("organizations")}
    assert "plan_id" in columnas
    fks = inspect(engine).get_foreign_keys("organizations")
    assert any(fk.get("referred_table") == "plans" for fk in fks)


def test_reconcile_agrega_wifi_calidad_con_datos(tmp_path, monkeypatch):
    db = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db}")
    _crear_esquema_legacy(engine)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    cfg = _config()

    command.stamp(cfg, REVISION_INICIAL)
    command.upgrade(cfg, "head")

    columnas = {c["name"] for c in inspect(engine).get_columns("device_status_logs")}
    assert "wifi_calidad" in columnas
    with engine.connect() as conn:
        filas = conn.execute(text("SELECT count(*) FROM device_status_logs")).scalar()
        wifi = conn.execute(text("SELECT wifi_calidad FROM device_status_logs WHERE id = 1")).scalar()
    assert filas == 1
    assert wifi is None


def test_upgrade_head_idempotente(tmp_path, monkeypatch):
    db = tmp_path / "nueva.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    cfg = _config()

    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db}")
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert version == REVISION_HEAD


def test_downgrade_revierte_reconciliacion(tmp_path, monkeypatch):
    db = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db}")
    _crear_esquema_legacy(engine)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    cfg = _config()

    command.stamp(cfg, REVISION_INICIAL)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, REVISION_INICIAL)

    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert version == REVISION_INICIAL

    inspector = inspect(engine)
    columnas_users = {c["name"] for c in inspector.get_columns("users")}
    columnas_orgs = {c["name"] for c in inspector.get_columns("organizations")}
    columnas_status = {c["name"] for c in inspector.get_columns("device_status_logs")}
    assert "role" not in columnas_users
    assert "plan_id" not in columnas_orgs
    assert "wifi_calidad" not in columnas_status
    indices = {i["name"] for i in inspector.get_indexes("telemetry_instantaneous")}
    assert "idx_telemetry_inst_dev_time" not in indices


def test_upgrade_agrega_desbalance_tension(tmp_path, monkeypatch):
    db = tmp_path / "test_desbalance.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    cfg = _config()

    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db}")
    inspector = inspect(engine)
    columnas = {c["name"] for c in inspector.get_columns("telemetry_instantaneous")}
    assert "desbalance_tension_porcentaje" in columnas
    assert "current_n" in columnas
