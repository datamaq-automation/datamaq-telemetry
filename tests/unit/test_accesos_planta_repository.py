"""tests/unit/test_accesos_planta_repository.py — Repositorio SQLAlchemy de accesos usuario↔planta, con SQLite en memoria."""

from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.domain.auth.entities import AccesoPlantaUsuario
from src.infrastructure.sqlalchemy.models import Base, UserModel
from src.infrastructure.sqlalchemy.repositories.accesos_planta_repository import (
    MySQLAccesosPlantaRepository,
)

USUARIO_ID = "user-1"
OTRO_USUARIO_ID = "user-2"


@pytest.fixture()
def db() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(UserModel(id=USUARIO_ID, username="operador1", password_hash="hash"))
    session.add(UserModel(id=OTRO_USUARIO_ID, username="operador2", password_hash="hash"))
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _acceso(planta_id: str, puede_cambiar: bool = True) -> AccesoPlantaUsuario:
    return AccesoPlantaUsuario(
        usuario_id=USUARIO_ID,
        planta_id=planta_id,
        puede_cambiar=puede_cambiar,
        creado_en=datetime(2026, 9, 19, 10, 0, 0, tzinfo=timezone.utc),
    )


def test_listar_por_usuario_sin_accesos_devuelve_lista_vacia(db: Session):
    repo = MySQLAccesosPlantaRepository(db)

    assert repo.listar_por_usuario(USUARIO_ID) == []


def test_reemplazar_crea_accesos_y_los_lista_ordenados(db: Session):
    repo = MySQLAccesosPlantaRepository(db)

    resultado = repo.reemplazar(
        USUARIO_ID,
        [_acceso("planta-garin", puede_cambiar=True), _acceso("planta-tigre", puede_cambiar=False)],
    )

    assert len(resultado) == 2
    plantas = {a.planta_id for a in resultado}
    assert plantas == {"planta-garin", "planta-tigre"}
    acceso_tigre = next(a for a in resultado if a.planta_id == "planta-tigre")
    assert acceso_tigre.puede_cambiar is False


def test_reemplazar_borra_accesos_previos_del_usuario(db: Session):
    repo = MySQLAccesosPlantaRepository(db)
    repo.reemplazar(USUARIO_ID, [_acceso("planta-garin")])

    resultado = repo.reemplazar(USUARIO_ID, [_acceso("planta-tigre")])

    assert [a.planta_id for a in resultado] == ["planta-tigre"]


def test_reemplazar_no_afecta_accesos_de_otro_usuario(db: Session):
    repo = MySQLAccesosPlantaRepository(db)
    repo.reemplazar(USUARIO_ID, [_acceso("planta-garin")])

    otro_acceso = AccesoPlantaUsuario(
        usuario_id=OTRO_USUARIO_ID,
        planta_id="planta-tigre",
        puede_cambiar=True,
        creado_en=datetime(2026, 9, 19, 10, 0, 0, tzinfo=timezone.utc),
    )
    repo.reemplazar(OTRO_USUARIO_ID, [otro_acceso])

    assert [a.planta_id for a in repo.listar_por_usuario(USUARIO_ID)] == ["planta-garin"]
    assert [a.planta_id for a in repo.listar_por_usuario(OTRO_USUARIO_ID)] == ["planta-tigre"]
