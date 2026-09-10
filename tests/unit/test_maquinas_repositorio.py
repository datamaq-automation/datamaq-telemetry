"""Repositorio SQLAlchemy de máquinas: filtro por organización, con SQLite en memoria."""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.domain.disponibilidad.entities import Maquina
from src.infrastructure.sqlalchemy.models import (
    Base,
    DeviceModel,
    FacilityModel,
    OrganizationModel,
)
from src.infrastructure.sqlalchemy.repositories.disponibilidad_repository import MySQLMaquinasRepository

ORG_A = "org-a"
ORG_B = "org-b"
PLANTA_A = "planta-a"
PLANTA_B = "planta-b"
DEVICE_A = "dev-a"
DEVICE_B = "dev-b"


@pytest.fixture()
def db() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(OrganizationModel(id=ORG_A, name="Org A"))
    session.add(OrganizationModel(id=ORG_B, name="Org B"))
    session.add(FacilityModel(id=PLANTA_A, organization_id=ORG_A, name="Planta A"))
    session.add(FacilityModel(id=PLANTA_B, organization_id=ORG_B, name="Planta B"))
    session.add(DeviceModel(id=DEVICE_A, facility_id=PLANTA_A, device_uid="AA:BB:CC:00:00:01", name="Medidor A"))
    session.add(DeviceModel(id=DEVICE_B, facility_id=PLANTA_B, device_uid="AA:BB:CC:00:00:02", name="Medidor B"))
    session.commit()
    try:
        yield session
    finally:
        session.close()


class TestMySQLMaquinasRepositoryListar:
    def test_sin_filtro_devuelve_todas(self, db: Session):
        repo = MySQLMaquinasRepository(db)
        repo.guardar(Maquina(id="m1", dispositivo_id=DEVICE_A, nombre="Máquina A"))
        repo.guardar(Maquina(id="m2", dispositivo_id=DEVICE_B, nombre="Máquina B"))

        resultado = repo.listar()

        assert {m.id for m in resultado} == {"m1", "m2"}

    def test_filtra_por_organizacion(self, db: Session):
        repo = MySQLMaquinasRepository(db)
        repo.guardar(Maquina(id="m1", dispositivo_id=DEVICE_A, nombre="Máquina A"))
        repo.guardar(Maquina(id="m2", dispositivo_id=DEVICE_B, nombre="Máquina B"))

        resultado_a = repo.listar(organizacion_id=ORG_A)
        resultado_b = repo.listar(organizacion_id=ORG_B)

        assert [m.id for m in resultado_a] == ["m1"]
        assert [m.id for m in resultado_b] == ["m2"]

    def test_organizacion_sin_maquinas_devuelve_vacio(self, db: Session):
        repo = MySQLMaquinasRepository(db)
        repo.guardar(Maquina(id="m1", dispositivo_id=DEVICE_A, nombre="Máquina A"))

        assert repo.listar(organizacion_id=ORG_B) == []
