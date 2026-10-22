"""tests/unit/test_consolidar_alertas_duplicadas.py — Script idempotente que consolida alertas abiertas duplicadas (#19)."""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from scripts.consolidar_alertas_duplicadas import consolidar
from src.infrastructure.sqlalchemy.models import Base, DeviceAlertModel, DeviceModel

T0 = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)
AHORA = datetime(2026, 10, 11, 23, 0, tzinfo=timezone.utc)


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sesion = sessionmaker(bind=engine)()
    sesion.add_all(
        [
            DeviceModel(id="bf2c", device_uid="AA0000BF2C", name="Durax"),
            DeviceModel(id="bbb0", device_uid="F8B3B7C0BBB0", name="SmartPlus #1", esta_activo=False),
        ]
    )
    sesion.commit()
    yield sesion
    sesion.close()


def _alerta(db: Session, device: str = "bf2c", tipo: str = "SOBRECOMPENSACION_REACTIVA", horas: int = 0, **kw):
    # BigInteger autoincrement no se traduce a INTEGER PRIMARY KEY en SQLite: el id va explícito.
    a = DeviceAlertModel(
        id=(db.query(DeviceAlertModel).count() + 1),
        device_id=device,
        alert_type=tipo,
        severity="WARNING",
        message=f"Q a las {horas} h",
        triggered_at=T0 + timedelta(hours=horas),
        measured_value=Decimal(-horas),
        **kw,
    )
    db.add(a)
    db.commit()
    return a


def _abiertas(db: Session) -> list[DeviceAlertModel]:
    return db.query(DeviceAlertModel).filter(DeviceAlertModel.is_resolved.is_(False)).all()


def test_dry_run_no_escribe(db):
    for h in range(3):
        _alerta(db, horas=h)

    grupos = consolidar(db, aplicar=False, ahora=AHORA)

    assert len(grupos) == 1 and len(grupos[0].resueltas_ids) == 2
    assert len(_abiertas(db)) == 3


def test_aplicar_deja_la_mas_antigua_con_las_ocurrencias_y_los_valores_mas_recientes(db):
    primera = _alerta(db, horas=0)
    for h in range(1, 116):
        _alerta(db, horas=h)

    consolidar(db, aplicar=True, ahora=AHORA)

    abiertas = _abiertas(db)
    assert [a.id for a in abiertas] == [primera.id]
    conservada = abiertas[0]
    assert conservada.occurrences == 116
    assert conservada.last_detected_at == T0 + timedelta(hours=115)
    assert conservada.message == "Q a las 115 h"
    assert conservada.measured_value == Decimal(-115)
    resuelta = db.query(DeviceAlertModel).filter(DeviceAlertModel.id != primera.id).first()
    assert resuelta is not None and resuelta.resolved_at == AHORA
    assert resuelta.notes == f"Consolidada en la alerta #{primera.id} (#19)."


def test_es_idempotente(db):
    for h in range(5):
        _alerta(db, horas=h)

    consolidar(db, aplicar=True, ahora=AHORA)
    estado = [(a.id, a.is_resolved, a.occurrences, a.notes) for a in db.query(DeviceAlertModel).order_by("id")]
    segunda = consolidar(db, aplicar=True, ahora=AHORA + timedelta(days=1))

    assert segunda == []
    assert [(a.id, a.is_resolved, a.occurrences, a.notes) for a in db.query(DeviceAlertModel).order_by("id")] == estado


def test_suma_las_ocurrencias_ya_registradas(db):
    _alerta(db, horas=0, occurrences=10)
    _alerta(db, horas=1, occurrences=5, last_detected_at=T0 + timedelta(hours=30))

    consolidar(db, aplicar=True, ahora=AHORA)

    (conservada,) = _abiertas(db)
    assert conservada.occurrences == 15
    assert conservada.last_detected_at == T0 + timedelta(hours=30)


def test_tipos_y_fases_distintos_no_se_mezclan(db):
    _alerta(db, tipo="BAJA_TENSION", phase="R")
    _alerta(db, tipo="BAJA_TENSION", phase="S", horas=1)
    _alerta(db, tipo="SOBRECOMPENSACION_REACTIVA", horas=2)

    assert consolidar(db, aplicar=True, ahora=AHORA) == []
    assert len(_abiertas(db)) == 3


def test_excluye_dispositivos_inactivos_salvo_que_se_pida(db):
    """El SmartPlus #1 (is_active=0) espera una decisión del dueño: por defecto no se toca."""
    for h in range(3):
        _alerta(db, device="bbb0", horas=h)

    assert consolidar(db, aplicar=True, ahora=AHORA) == []
    assert len(_abiertas(db)) == 3
    assert len(consolidar(db, aplicar=False, ahora=AHORA, incluir_inactivos=True)) == 1


def test_no_toca_las_resueltas(db):
    _alerta(db, horas=0)
    _alerta(db, horas=1, is_resolved=True, resolved_at=T0 + timedelta(hours=2))

    assert consolidar(db, aplicar=True, ahora=AHORA) == []
