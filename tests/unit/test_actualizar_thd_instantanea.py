"""tests/unit/test_actualizar_thd_instantanea.py — THD de /harmonics sobre la última fila persistida."""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from itertools import count

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from src.domain.telemetria.entities import LecturaInstantanea, MedicionFase
from src.domain.telemetria.servicios.harmonics_thd import ThdFase
from src.domain.telemetria.value_objects import Corriente, Tension
from src.infrastructure.sqlalchemy.models import Base, TelemetryInstantaneousModel
from src.infrastructure.sqlalchemy.mysql_repositories import MySQLTelemetriaRepository

DISPOSITIVO = "2812d2af-b1cf-4daa-a379-40102fdb152d"
MOMENTO = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)


_siguiente_id = count(1)


def _asignar_pk(session: Session, flush_context, instances) -> None:
    # SQLite no autoincrementa la BigInteger del modelo: se asigna la PK a mano, como en test_mysql_repositories.
    for obj in session.new:
        if isinstance(obj, TelemetryInstantaneousModel) and obj.id is None:
            obj.id = next(_siguiente_id)


@pytest.fixture()
def db() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    event.listen(session, "before_flush", _asignar_pk)
    try:
        yield session
    finally:
        session.close()


def _lectura(registrado_en: datetime) -> LecturaInstantanea:
    fase = MedicionFase(tension=Tension(220.0), corriente=Corriente(60.0))
    return LecturaInstantanea(
        id=0,
        dispositivo_id=DISPOSITIVO,
        registrado_en=registrado_en,
        fase_r=fase,
        fase_s=fase,
        fase_t=fase,
    )


def _persistir(db: Session, registrado_en: datetime) -> None:
    MySQLTelemetriaRepository(db).guardar_instantanea(_lectura(registrado_en))


def _thd_completo() -> dict[str, ThdFase]:
    return {
        "R": ThdFase(thd_v_pct=2.56, thd_i_pct=992.52),
        "S": ThdFase(thd_v_pct=2.59, thd_i_pct=530.99),
        "T": ThdFase(thd_v_pct=2.56, thd_i_pct=300.0),
    }


def test_actualiza_la_fila_mas_reciente_dentro_de_la_ventana(db: Session):
    _persistir(db, MOMENTO - timedelta(seconds=30))
    repo = MySQLTelemetriaRepository(db)
    assert repo.actualizar_thd_instantanea(DISPOSITIVO, MOMENTO, 360, _thd_completo()) is True
    fila = db.query(TelemetryInstantaneousModel).one()
    assert fila.thd_v_r == Decimal("2.56")
    assert fila.thd_i_r == Decimal("992.52")
    assert fila.thd_i_t == Decimal("300.00")


def test_sin_fila_en_la_ventana_no_guarda_nada(db: Session):
    _persistir(db, MOMENTO - timedelta(seconds=361))
    repo = MySQLTelemetriaRepository(db)
    assert repo.actualizar_thd_instantanea(DISPOSITIVO, MOMENTO, 360, _thd_completo()) is False
    fila = db.query(TelemetryInstantaneousModel).one()
    assert fila.thd_i_r is None


def test_no_toca_filas_posteriores_al_momento(db: Session):
    _persistir(db, MOMENTO + timedelta(seconds=5))
    repo = MySQLTelemetriaRepository(db)
    assert repo.actualizar_thd_instantanea(DISPOSITIVO, MOMENTO, 360, _thd_completo()) is False


def test_fase_faltante_no_pisa_los_thd_de_las_otras_fases(db: Session):
    _persistir(db, MOMENTO - timedelta(seconds=10))
    repo = MySQLTelemetriaRepository(db)
    repo.actualizar_thd_instantanea(DISPOSITIVO, MOMENTO, 360, {"S": ThdFase(thd_v_pct=2.59, thd_i_pct=530.99)})
    fila = db.query(TelemetryInstantaneousModel).one()
    assert fila.thd_i_s == Decimal("530.99")
    assert fila.thd_i_r is None
    assert fila.thd_i_t is None


def test_otro_dispositivo_no_se_actualiza(db: Session):
    _persistir(db, MOMENTO - timedelta(seconds=10))
    repo = MySQLTelemetriaRepository(db)
    assert repo.actualizar_thd_instantanea("otro-dispositivo", MOMENTO, 360, _thd_completo()) is False
