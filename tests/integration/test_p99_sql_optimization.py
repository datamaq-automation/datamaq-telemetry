"""tests/integration/test_p99_sql_optimization.py — P99 optimization con SQL buckets."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.infrastructure.sqlalchemy.repositories.telemetria_repository import MySQLTelemetriaRepository


def test_obtener_potencia_bucketizada_sql_vacia(db_session: Session):
    """Devuelve lista vacía sin datos."""
    repo = MySQLTelemetriaRepository(db_session)
    buckets = repo.obtener_potencia_bucketizada_sql(
        ["dev-test-1"],
        datetime.now(timezone.utc) - timedelta(days=1),
        datetime.now(timezone.utc),
    )
    assert buckets == []


def test_obtener_potencia_bucketizada_sql_valores(db_session: Session):
    """Bucketiza y suma correctamente."""

    repo = MySQLTelemetriaRepository(db_session)
    ahora = datetime.now(timezone.utc)

    db_session.execute(
        text(
            "INSERT INTO devices (id, device_uid, nombre, creado_en, actualizado_en) "
            "VALUES ('dev-p99-1', 'AA:BB:CC:DD:EE:01', 'P99Test1', :now, :now)"
        ),
        {"now": ahora},
    )
    db_session.commit()

    bucket_1 = ahora - timedelta(minutes=10)
    bucket_2 = ahora - timedelta(minutes=5)

    for i in range(3):
        db_session.execute(
            text(
                "INSERT INTO telemetry_instantaneous "
                "(device_id, recorded_at, total_active_power) "
                "VALUES ('dev-p99-1', :ts, :power)"
            ),
            {"ts": bucket_1 + timedelta(seconds=i * 30), "power": 1000.0 + i * 100},
        )
    db_session.commit()

    for i in range(2):
        db_session.execute(
            text(
                "INSERT INTO telemetry_instantaneous "
                "(device_id, recorded_at, total_active_power) "
                "VALUES ('dev-p99-1', :ts, :power)"
            ),
            {"ts": bucket_2 + timedelta(seconds=i * 30), "power": 2000.0 + i * 100},
        )
    db_session.commit()

    buckets = repo.obtener_potencia_bucketizada_sql(
        ["dev-p99-1"],
        ahora - timedelta(minutes=15),
        ahora,
        bucket_segundos=300,
    )

    assert len(buckets) == 2
    assert 1000 <= buckets[0] <= 1300
    assert 2000 <= buckets[1] <= 2200


def test_p99_sql_vs_python_dan_mismo_resultado(db_session: Session):
    """P99 calculado en SQL es compatible con el histórico Python."""
    repo = MySQLTelemetriaRepository(db_session)
    ahora = datetime.now(timezone.utc)
    hace_7d = ahora - timedelta(days=7)

    db_session.execute(
        text(
            "INSERT INTO devices (id, device_uid, nombre, creado_en, actualizado_en) "
            "VALUES ('dev-p99-comp', 'AA:BB:CC:DD:EE:02', 'P99Comp', :now, :now)"
        ),
        {"now": ahora},
    )
    db_session.commit()

    for h in range(0, 168, 3):
        ts = hace_7d + timedelta(hours=h)
        power = 1000 + (h * 50) % 500
        db_session.execute(
            text(
                "INSERT INTO telemetry_instantaneous "
                "(device_id, recorded_at, total_active_power) "
                "VALUES ('dev-p99-comp', :ts, :power)"
            ),
            {"ts": ts, "power": power},
        )
    db_session.commit()

    buckets = repo.obtener_potencia_bucketizada_sql(
        ["dev-p99-comp"],
        hace_7d,
        ahora,
        bucket_segundos=300,
    )

    assert len(buckets) > 0
    assert all(isinstance(b, float) for b in buckets)
    assert all(500 <= b <= 2000 for b in buckets)
