"""tests/integration/conftest.py — Fixtures para tests de integración."""

from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture()
def db_session() -> Iterator[Session]:
    """SQLite en memoria para tests de integración."""
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    with engine.connect() as conn:
        conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS devices (
                id VARCHAR(36) PRIMARY KEY,
                device_uid VARCHAR(50) NOT NULL,
                nombre VARCHAR(255),
                planta_id VARCHAR(36),
                tipo_instalacion VARCHAR(50),
                esta_activo BOOLEAN DEFAULT 1,
                estado VARCHAR(50),
                visto_por_ultima_vez DATETIME,
                creado_en DATETIME NOT NULL,
                actualizado_en DATETIME NOT NULL
            )
            """
            )
        )
        conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS telemetry_instantaneous (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id VARCHAR(36) NOT NULL,
                recorded_at DATETIME NOT NULL,
                total_active_power DECIMAL(12, 2),
                FOREIGN KEY(device_id) REFERENCES devices(id) ON DELETE CASCADE
            )
            """
            )
        )
        conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS telemetria_anomalias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id VARCHAR(36) NOT NULL,
                recorded_at DATETIME NOT NULL,
                error_s REAL NOT NULL,
                flag_tipo VARCHAR(50) NOT NULL,
                contador_consecutivos INTEGER NOT NULL DEFAULT 1,
                estado VARCHAR(50) NOT NULL DEFAULT 'active',
                creado_en DATETIME NOT NULL,
                actualizado_en DATETIME NOT NULL,
                FOREIGN KEY(device_id) REFERENCES devices(id) ON DELETE CASCADE
            )
            """
            )
        )
        conn.commit()

    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    ahora = datetime.now(timezone.utc)
    session.execute(
        text(
            "INSERT INTO devices (id, device_uid, nombre, creado_en, actualizado_en) "
            "VALUES ('dev-001', 'AA:BB:CC:DD:EE:FF', 'Test', :now, :now)"
        ),
        {"now": ahora},
    )
    session.commit()

    try:
        yield session
    finally:
        session.close()
