"""tests/unit/test_repositorio_auditoria_cambios_ti.py.
Repositorio SQLAlchemy de la auditoría de cambios de TI sobre SQLite en memoria."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.infrastructure.sqlalchemy.models import AuditoriaChangesTIModel, Base, DeviceModel
from src.infrastructure.sqlalchemy.repositories.auditoria_cambios_ti_repository import AuditoriaCambiosTIRepository

DEVICE_ID = "c91713f1-0621-4a33-9279-c5327a317d96"


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(
        DeviceModel(
            id=DEVICE_ID,
            device_uid="EC:C9:FF:B5:7F:20",
            name="Powermeter 369",
            tag_location="TGBT Trafo 2",
            ct_phase_angle_offsets="R:-60,S:0",
            phases_with_ct="R,S",
            ct_inverted_phases="",
        )
    )
    session.add_all(
        [
            AuditoriaChangesTIModel(
                id=1,
                device_id=DEVICE_ID,
                tipo_cambio="correccion_angular",
                valor_anterior="R:180,S:-120",
                valor_nuevo="R:-60,S:0",
                commit_git="fdfea7d",
                timestamp=datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc),
            ),
            AuditoriaChangesTIModel(
                id=2,
                device_id=DEVICE_ID,
                tipo_cambio="polaridad",
                valor_nuevo="invertido",
                timestamp=datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc),
            ),
        ]
    )
    session.commit()
    yield session
    session.close()


def test_listar_devuelve_los_mas_recientes_primero(db: Session):
    registros = AuditoriaCambiosTIRepository(db).listar(None, None, None, None)
    assert [r["id"] for r in registros] == [1, 2]


def test_listar_filtra_por_tipo_y_por_rango(db: Session):
    repo = AuditoriaCambiosTIRepository(db)
    assert [r["id"] for r in repo.listar(None, "polaridad", None, None)] == [2]
    desde = datetime(2026, 10, 15, tzinfo=timezone.utc)
    assert [r["id"] for r in repo.listar(None, None, desde, None)] == [1]


def test_obtener_incluye_el_dispositivo_con_su_configuracion(db: Session):
    registro = AuditoriaCambiosTIRepository(db).obtener(1)
    assert registro is not None
    assert registro["valor_nuevo"] == "R:-60,S:0"
    assert registro["dispositivo"] == {
        "id": DEVICE_ID,
        "alias": "Powermeter 369",
        "ubicacion": "TGBT Trafo 2",
        "config_actual": {"correccion_angular_fases": "R:-60,S:0", "fases_con_ti": "R,S", "invertido": False},
    }


def test_obtener_devuelve_none_si_no_existe(db: Session):
    assert AuditoriaCambiosTIRepository(db).obtener(99) is None
