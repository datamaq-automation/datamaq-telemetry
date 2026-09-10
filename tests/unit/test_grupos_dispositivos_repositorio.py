"""Repositorio SQLAlchemy de grupos de dispositivos, con SQLite en memoria."""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from src.domain.telemetria.entities import GrupoDispositivos
from src.infrastructure.sqlalchemy.models import (
    Base,
    DeviceGroupMemberModel,
    DeviceModel,
    FacilityModel,
    OrganizationModel,
)
from src.infrastructure.sqlalchemy.repositories.grupos_dispositivos_repository import (
    MySQLGruposDispositivosRepository,
)

PLANTA_ID = "planta-1"
ORG_ID = "org-1"
DEVICE_1 = "dev-trafo-01"
DEVICE_2 = "dev-trafo-02"


@pytest.fixture()
def db() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    # SQLite no aplica ON DELETE CASCADE por default; en MySQL (producción) InnoDB sí lo
    # hace a nivel de motor, incluso con un DELETE bulk del ORM. Se activa acá para que el
    # test ejerza la misma garantía que corre en producción.
    event.listen(engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(OrganizationModel(id=ORG_ID, name="Org Test"))
    session.add(FacilityModel(id=PLANTA_ID, organization_id=ORG_ID, name="Planta Test"))
    session.add(DeviceModel(id=DEVICE_1, facility_id=PLANTA_ID, device_uid="AA:BB:CC:00:00:01", name="Trafo 1"))
    session.add(DeviceModel(id=DEVICE_2, facility_id=PLANTA_ID, device_uid="AA:BB:CC:00:00:02", name="Trafo 2"))
    session.commit()
    try:
        yield session
    finally:
        session.close()


class TestMySQLGruposDispositivosRepository:
    def test_crear_persiste_grupo_y_miembros(self, db: Session):
        repo = MySQLGruposDispositivosRepository(db)
        grupo = GrupoDispositivos(
            id="g1", planta_id=PLANTA_ID, nombre="Total Planta", dispositivos_ids=[DEVICE_1, DEVICE_2]
        )

        creado = repo.crear(grupo)

        assert creado.id == "g1"
        assert set(creado.dispositivos_ids) == {DEVICE_1, DEVICE_2}

    def test_obtener_por_id_inexistente_devuelve_none(self, db: Session):
        repo = MySQLGruposDispositivosRepository(db)
        assert repo.obtener_por_id("no-existe") is None

    def test_listar_por_planta_filtra_correctamente(self, db: Session):
        db.add(FacilityModel(id="otra-planta", organization_id=ORG_ID, name="Otra Planta"))
        db.commit()
        repo = MySQLGruposDispositivosRepository(db)
        repo.crear(GrupoDispositivos(id="g1", planta_id=PLANTA_ID, nombre="Grupo A"))
        repo.crear(GrupoDispositivos(id="g2", planta_id="otra-planta", nombre="Grupo B"))

        resultado = repo.listar_por_planta(PLANTA_ID)

        assert [g.id for g in resultado] == ["g1"]

    def test_agregar_miembro_es_idempotente(self, db: Session):
        repo = MySQLGruposDispositivosRepository(db)
        repo.crear(GrupoDispositivos(id="g1", planta_id=PLANTA_ID, nombre="Grupo A"))

        repo.agregar_miembro("g1", DEVICE_1)
        repo.agregar_miembro("g1", DEVICE_1)

        filas = db.query(DeviceGroupMemberModel).filter(DeviceGroupMemberModel.group_id == "g1").all()
        assert len(filas) == 1

    def test_quitar_miembro_que_no_es_miembro_no_falla(self, db: Session):
        repo = MySQLGruposDispositivosRepository(db)
        repo.crear(GrupoDispositivos(id="g1", planta_id=PLANTA_ID, nombre="Grupo A"))

        repo.quitar_miembro("g1", DEVICE_1)

        assert repo.obtener_por_id("g1").dispositivos_ids == []

    def test_eliminar_borra_grupo_y_miembros_en_cascada(self, db: Session):
        repo = MySQLGruposDispositivosRepository(db)
        repo.crear(GrupoDispositivos(id="g1", planta_id=PLANTA_ID, nombre="Grupo A", dispositivos_ids=[DEVICE_1]))

        repo.eliminar("g1")

        assert repo.obtener_por_id("g1") is None
        filas = db.query(DeviceGroupMemberModel).filter(DeviceGroupMemberModel.group_id == "g1").all()
        assert filas == []

    def test_listar_dispositivos_miembro_devuelve_entidades_completas(self, db: Session):
        repo = MySQLGruposDispositivosRepository(db)
        repo.crear(
            GrupoDispositivos(id="g1", planta_id=PLANTA_ID, nombre="Grupo A", dispositivos_ids=[DEVICE_1, DEVICE_2])
        )

        dispositivos = repo.listar_dispositivos_miembro("g1")

        assert {d.id for d in dispositivos} == {DEVICE_1, DEVICE_2}
        assert all(d.nombre for d in dispositivos)

    def test_listar_dispositivos_miembro_de_grupo_inexistente_devuelve_vacio(self, db: Session):
        repo = MySQLGruposDispositivosRepository(db)
        assert repo.listar_dispositivos_miembro("no-existe") == []
