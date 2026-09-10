"""Pruebas de la infraestructura de migraciones Alembic (specs/migraciones.md)."""

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command

RAIZ = Path(__file__).resolve().parents[2]
ALEMBIC_INI = RAIZ / "alembic.ini"
ENV_PY = RAIZ / "alembic" / "env.py"
REVISION_INICIAL = "209ce0774d59"
REVISION_HEAD = "h2i3j4k5l6m7"

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
    "unifilar_nodes",
    "facility_zones",
    "facility_device_layouts",
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
    assert "voltage_linea_V" in columnas
    assert "tension_neutro_estimada" in columnas
    assert "thd_v_r" in columnas
    assert "thd_i_r" in columnas
    assert "thd_v_s" in columnas
    assert "thd_i_s" in columnas
    assert "thd_v_t" in columnas
    assert "thd_i_t" in columnas
    assert "thd_v_promedio_porcentaje" in columnas
    assert "thd_i_total_porcentaje" in columnas

    columnas_alerts = {c["name"] for c in inspector.get_columns("device_alerts")}
    assert "phase" in columnas_alerts
    assert "measured_value" in columnas_alerts
    assert "threshold_value" in columnas_alerts
    assert "unit" in columnas_alerts
    assert "category" in columnas_alerts
    assert "notes" in columnas_alerts


def test_migraciones_tienen_una_sola_cabeza_lineal():
    from alembic.script import ScriptDirectory

    cfg = _config()
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert len(heads) == 1, f"Se detectaron múltiples ramas en Alembic: {heads}"
    assert heads[0] == REVISION_HEAD


def test_paridad_completa_modelos_orm_vs_migraciones_alembic(tmp_path, monkeypatch):
    """Garantiza que TODAS las tablas y columnas declaradas en Base.metadata existan en la BD tras 'upgrade head'."""
    from src.infrastructure.sqlalchemy.models import Base

    db = tmp_path / "parity_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    cfg = _config()

    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db}")
    inspector = inspect(engine)
    tablas_bd = set(inspector.get_table_names())

    discrepancias = []
    for nombre_tabla, tabla_orm in Base.metadata.tables.items():
        if nombre_tabla not in tablas_bd:
            discrepancias.append(f"Tabla '{nombre_tabla}' declarada en ORM pero falta en BD")
            continue

        columnas_bd = {c["name"] for c in inspector.get_columns(nombre_tabla)}
        columnas_orm = {c.name for c in tabla_orm.columns}

        faltantes_en_bd = columnas_orm - columnas_bd
        if faltantes_en_bd:
            discrepancias.append(
                f"Tabla '{nombre_tabla}': columnas en ORM ausentes en BD tras migraciones: {sorted(faltantes_en_bd)}"
            )

    assert not discrepancias, "\n".join(discrepancias)


def test_backfill_recalcula_potencia_aparente_y_fp(tmp_path, monkeypatch):
    """El backfill reescribe S = V·I y FP = P/S sobre las lecturas ya persistidas."""
    db = tmp_path / "backfill.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    cfg = _config()
    engine = create_engine(f"sqlite:///{db}")

    command.upgrade(cfg, "b8c9d0e1f2a3")

    with engine.begin() as conn:
        # Fila histórica sin potencia aparente: el firmware compacto nunca la publicó
        conn.execute(
            text(
                "INSERT INTO telemetry_instantaneous "
                "(id, device_id, created_at, recorded_at, voltage_r, current_r, active_power_r, total_active_power) "
                "VALUES (1, 'dev-1', '2026-09-01 23:20:00', '2026-09-01 23:20:00', 227.7, 0.9, 147.0, 147.0)"
            )
        )
        # Fila con la semántica vieja de hypot(P, Q), que debe quedar reescrita
        conn.execute(
            text(
                "INSERT INTO telemetry_instantaneous "
                "(id, device_id, created_at, recorded_at, voltage_r, current_r, active_power_r, apparent_power_r, power_factor_r) "
                "VALUES (2, 'dev-1', '2026-09-01 23:25:00', '2026-09-01 23:25:00', 200.0, 2.0, 300.0, 500.0, 0.6)"
            )
        )
        # Fila donde P supera V·I por redondeo del firmware: el FP debe quedar acotado
        conn.execute(
            text(
                "INSERT INTO telemetry_instantaneous "
                "(id, device_id, created_at, recorded_at, voltage_r, current_r, active_power_r) "
                "VALUES (3, 'dev-1', '2026-09-01 23:30:00', '2026-09-01 23:30:00', 100.0, 1.0, 250.0)"
            )
        )

    command.upgrade(cfg, "head")

    with engine.connect() as conn:
        filas = {
            r[0]: (float(r[1]), float(r[2]))
            for r in conn.execute(
                text("SELECT id, apparent_power_r, power_factor_r FROM telemetry_instantaneous ORDER BY id")
            )
        }

    assert filas[1] == (204.93, 0.72)
    assert filas[2] == (400.0, 0.75)  # hypot daba 500.0 y FP 0.6
    assert filas[3] == (100.0, 1.0)  # acotado, no 2.5

    with engine.connect() as conn:
        total = conn.execute(
            text("SELECT total_apparent_power, total_power_factor FROM telemetry_instantaneous WHERE id = 1")
        ).first()
    assert total is not None
    assert float(total[0]) == 204.93
    assert float(total[1]) == 0.72


def test_backfill_es_idempotente(tmp_path, monkeypatch):
    db = tmp_path / "backfill_idem.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    cfg = _config()
    engine = create_engine(f"sqlite:///{db}")

    command.upgrade(cfg, "b8c9d0e1f2a3")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO telemetry_instantaneous "
                "(id, device_id, created_at, recorded_at, voltage_r, current_r, active_power_r) "
                "VALUES (1, 'dev-1', '2026-09-01 23:20:00', '2026-09-01 23:20:00', 227.7, 0.9, 147.0)"
            )
        )

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "b8c9d0e1f2a3")
    command.upgrade(cfg, "head")

    with engine.connect() as conn:
        fila = conn.execute(
            text("SELECT apparent_power_r, power_factor_r FROM telemetry_instantaneous WHERE id = 1")
        ).first()
    assert fila is not None
    assert (float(fila[0]), float(fila[1])) == (204.93, 0.72)


@pytest.mark.parametrize("installation_type,phases_with_ct", [("1P2W", "R"), ("CONSUMO", "R")])
def test_backfill_monofasico_anula_columnas_trifasicas(tmp_path, monkeypatch, installation_type, phases_with_ct):
    """El backfill anula las 4 columnas derivadas trifásicas solo en dispositivos monofásicos."""
    db = tmp_path / "backfill_mono.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    cfg = _config()
    engine = create_engine(f"sqlite:///{db}")

    command.upgrade(cfg, "c9d0e1f2a3b4")

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO devices "
                "(id, device_uid, name, model, is_active, status, installation_type, phases_with_ct, created_at, updated_at) "
                "VALUES ('dev-mono', 'MONO-UID', 'Mono', 'SmartPlus', 1, 'ONLINE', :it, :pc, '2026-09-01 00:00:00', '2026-09-01 00:00:00')"
            ),
            {"it": installation_type, "pc": phases_with_ct},
        )
        conn.execute(
            text(
                "INSERT INTO devices "
                "(id, device_uid, name, model, is_active, status, installation_type, phases_with_ct, created_at, updated_at) "
                "VALUES ('dev-tri', 'TRI-UID', 'Tri', 'SmartPlus', 1, 'ONLINE', 'CONSUMO', 'R,S,T', '2026-09-01 00:00:00', '2026-09-01 00:00:00')"
            )
        )
        # Lectura monofásica con residuales trifásicos que el backfill debe anular
        conn.execute(
            text(
                "INSERT INTO telemetry_instantaneous "
                "(id, device_id, created_at, recorded_at, desbalance_tension_porcentaje, current_n, voltage_linea_V, tension_neutro_estimada) "
                "VALUES (1, 'dev-mono', '2026-09-01 23:00:00', '2026-09-01 23:00:00', 12.3, 4.5, 395.0, 1.2)"
            )
        )
        # Lectura trifásica que debe conservar sus columnas
        conn.execute(
            text(
                "INSERT INTO telemetry_instantaneous "
                "(id, device_id, created_at, recorded_at, desbalance_tension_porcentaje, current_n, voltage_linea_V, tension_neutro_estimada) "
                "VALUES (2, 'dev-tri', '2026-09-01 23:00:00', '2026-09-01 23:00:00', 1.5, 0.4, 395.0, 0.0)"
            )
        )

    command.upgrade(cfg, "head")

    with engine.connect() as conn:
        mono = conn.execute(
            text(
                "SELECT desbalance_tension_porcentaje, current_n, voltage_linea_V, tension_neutro_estimada "
                "FROM telemetry_instantaneous WHERE id = 1"
            )
        ).first()
        tri = conn.execute(
            text(
                "SELECT desbalance_tension_porcentaje, current_n, voltage_linea_V, tension_neutro_estimada "
                "FROM telemetry_instantaneous WHERE id = 2"
            )
        ).first()

    assert mono is not None
    assert mono[0] is None
    assert mono[1] is None
    assert mono[2] is None
    assert mono[3] is None

    assert tri is not None
    assert float(tri[0]) == 1.5
    assert float(tri[1]) == 0.4
    assert float(tri[2]) == 395.0
    assert float(tri[3]) == 0.0
