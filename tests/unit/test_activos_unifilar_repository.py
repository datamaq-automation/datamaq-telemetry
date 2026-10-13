"""tests/unit/test_activos_unifilar_repository.py — Tests para MySQLActivosUnifilarRepository."""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.domain.telemetria.entities import ActivoUnifilar
from src.domain.telemetria.value_objects import TipoActivoUnifilar
from src.infrastructure.sqlalchemy.models import Base, FacilityModel, OrganizationModel
from src.infrastructure.sqlalchemy.repositories.activos_unifilar_repository import (
    MySQLActivosUnifilarRepository,
)


@pytest.fixture()
def db() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()

    # Fixtures de organización y planta
    # El nombre de la organización vive en data/organizaciones.yml, no en la BD.
    org = OrganizationModel(id="org-1")
    planta = FacilityModel(id="planta-1", organization_id="org-1", name="Planta Central")
    session.add_all([org, planta])
    session.commit()

    yield session

    session.close()
    Base.metadata.drop_all(engine)


def test_guardar_y_obtener_por_id(db: Session) -> None:
    repo = MySQLActivosUnifilarRepository(db)

    activo = ActivoUnifilar(
        id="tgbt-01",
        planta_id="planta-1",
        nombre="TGBT Principal",
        tipo=TipoActivoUnifilar.TGBT,
        tension_nominal_v=400.0,
        parent_id="trafo-01",
        device_id=None,
        potencia_nominal_kw=250.0,
        capacidad_nominal_kva=315.0,
        categoria_uso="Fuerza Motriz",
        uso_significativo=True,
        posicion_x=20.5,
        posicion_y=40.0,
        ancho=100.0,
        alto=80.0,
        orden=1,
    )

    guardado = repo.guardar(activo)
    assert guardado.id == "tgbt-01"
    assert guardado.nombre == "TGBT Principal"
    assert guardado.tipo == TipoActivoUnifilar.TGBT
    assert guardado.uso_significativo is True

    recuperado = repo.obtener_por_id("tgbt-01")
    assert recuperado is not None
    assert recuperado.id == "tgbt-01"
    assert recuperado.planta_id == "planta-1"
    assert recuperado.tension_nominal_v == 400.0
    assert recuperado.parent_id == "trafo-01"
    assert recuperado.potencia_nominal_kw == 250.0
    assert recuperado.categoria_uso == "Fuerza Motriz"


def test_obtener_inexistente_retorna_none(db: Session) -> None:
    repo = MySQLActivosUnifilarRepository(db)
    assert repo.obtener_por_id("no-existe") is None


def test_guardar_actualiza_existente(db: Session) -> None:
    repo = MySQLActivosUnifilarRepository(db)

    activo = ActivoUnifilar(
        id="ts-01",
        planta_id="planta-1",
        nombre="Tablero Antiguo",
        tipo=TipoActivoUnifilar.TABLERO_SECCIONAL,
        tension_nominal_v=380.0,
        orden=5,
    )
    repo.guardar(activo)

    # Actualización
    activo.nombre = "Tablero Iluminación Actualizado"
    activo.categoria_uso = "Iluminación"
    activo.orden = 2
    repo.guardar(activo)

    actualizado = repo.obtener_por_id("ts-01")
    assert actualizado is not None
    assert actualizado.nombre == "Tablero Iluminación Actualizado"
    assert actualizado.categoria_uso == "Iluminación"
    assert actualizado.orden == 2


def test_listar_por_planta_ordenado(db: Session) -> None:
    repo = MySQLActivosUnifilarRepository(db)

    a1 = ActivoUnifilar(
        id="act-b",
        planta_id="planta-1",
        nombre="B Tablero",
        tipo=TipoActivoUnifilar.TABLERO_SECCIONAL,
        tension_nominal_v=380.0,
        orden=2,
    )
    a2 = ActivoUnifilar(
        id="act-a",
        planta_id="planta-1",
        nombre="A Cabecera",
        tipo=TipoActivoUnifilar.TRANSFORMADOR,
        tension_nominal_v=13200.0,
        orden=1,
    )
    a3 = ActivoUnifilar(
        id="act-c",
        planta_id="planta-1",
        nombre="C Carga",
        tipo=TipoActivoUnifilar.MAQUINA,
        tension_nominal_v=380.0,
        orden=3,
    )
    repo.guardar_lote([a1, a2, a3])

    lista = repo.listar_por_planta("planta-1")
    assert len(lista) == 3
    assert [a.id for a in lista] == ["act-a", "act-b", "act-c"]

    # Otra planta sin activos
    assert repo.listar_por_planta("otra-planta") == []


def test_eliminar_activo(db: Session) -> None:
    repo = MySQLActivosUnifilarRepository(db)

    activo = ActivoUnifilar(
        id="ts-eliminar",
        planta_id="planta-1",
        nombre="Para Borrar",
        tipo=TipoActivoUnifilar.LINEA,
        tension_nominal_v=380.0,
    )
    repo.guardar(activo)
    assert repo.obtener_por_id("ts-eliminar") is not None

    eliminado = repo.eliminar("ts-eliminar")
    assert eliminado is True
    assert repo.obtener_por_id("ts-eliminar") is None

    # Eliminar uno que ya no existe
    assert repo.eliminar("ts-eliminar") is False
