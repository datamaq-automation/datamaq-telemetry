"""tests/unit/test_alta_dispositivo_por_planta.py — Issue datamaq#132: POST /api/v1/dispositivos respeta la planta destino.

El alta solo validaba el cupo de la organización dueña de la planta, nunca que quien llama perteneciera a ella:
un operador de org-a registraba un medidor en una planta de org-b. App completa con repositorios SQLAlchemy reales
sobre SQLite en memoria y la política real de acceso a plantas.
"""

from collections.abc import Callable, Iterator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.application.use_cases.gestionar_acceso_plantas import GestionarAccesoPlantasUseCase
from src.domain.auth.entities import AccesoPlantaUsuario
from src.domain.telemetria.entities import Planta
from src.infrastructure.fastapi.auth_dependencies import get_acceso_plantas_use_case
from src.infrastructure.fastapi.dependencies import get_usuario_actual
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.sqlalchemy.database import get_db_session
from src.infrastructure.sqlalchemy.models import Base, DeviceModel, FacilityModel, OrganizationModel

PLANTA_ORG = {"planta-a1": "org-a", "planta-a2": "org-a", "planta-b": "org-b"}
OPERADOR_A = {"sub": "u1", "rol": "operador", "org": "org-a"}


@pytest.fixture()
def db() -> Iterator[Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    for org in ("org-a", "org-b"):
        session.add(OrganizationModel(id=org))
    for planta, org in PLANTA_ORG.items():
        session.add(FacilityModel(id=planta, organization_id=org, name=planta))
    session.commit()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def cliente(db: Session, monkeypatch) -> Callable[..., TestClient]:
    for modulo in ("planta_ownership", "routes.dispositivos_router"):
        monkeypatch.setattr(f"src.infrastructure.fastapi.{modulo}.get_settings", lambda: MagicMock(AUTH_REQUIRED=True))
    plantas = [Planta(id=p, organizacion_id=o, nombre=p) for p, o in PLANTA_ORG.items()]
    repo_org = MagicMock()
    repo_org.listar_plantas.side_effect = lambda org=None: [
        p for p in plantas if org is None or p.organizacion_id == org
    ]

    def _crear(claims: dict, plantas_asignadas: list[str] | None = None) -> TestClient:
        accesos = [
            AccesoPlantaUsuario(usuario_id="u1", planta_id=p, puede_cambiar=False) for p in plantas_asignadas or []
        ]
        acceso = GestionarAccesoPlantasUseCase(MagicMock(listar_por_usuario=lambda uid: accesos), repo_org)
        app = create_app()
        app.dependency_overrides[get_db_session] = lambda: db
        app.dependency_overrides[get_usuario_actual] = lambda: claims
        app.dependency_overrides[get_acceso_plantas_use_case] = lambda: acceso
        return TestClient(app)

    return _crear


def _alta(client: TestClient, uid: str, planta_id: str | None):
    cuerpo = {"device_uid": uid, "nombre": "medidor nuevo"}
    if planta_id is not None:
        cuerpo["planta_id"] = planta_id
    return client.post("/api/v1/dispositivos", json=cuerpo)


def _en_planta(db: Session, planta_id: str) -> int:
    return db.query(DeviceModel).filter(DeviceModel.facility_id == planta_id).count()


def test_un_operador_no_registra_un_medidor_en_la_planta_de_otra_organizacion(cliente, db):
    r = _alta(cliente(OPERADOR_A), "AABBCCDDEE01", "planta-b")

    assert r.status_code == 404
    assert _en_planta(db, "planta-b") == 0


def test_un_operador_registra_un_medidor_en_una_planta_de_su_organizacion(cliente, db):
    r = _alta(cliente(OPERADOR_A), "AABBCCDDEE02", "planta-a1")

    assert r.status_code == 200
    assert _en_planta(db, "planta-a1") == 1


def test_un_usuario_restringido_a_una_planta_no_registra_en_otra_de_su_organizacion(cliente, db):
    client = cliente(OPERADOR_A, plantas_asignadas=["planta-a1"])

    assert _alta(client, "AABBCCDDEE03", "planta-a2").status_code == 404
    assert _en_planta(db, "planta-a2") == 0
    assert _alta(client, "AABBCCDDEE04", "planta-a1").status_code == 200


def test_una_planta_inexistente_responde_404_a_un_usuario_de_organizacion(cliente):
    assert _alta(cliente(OPERADOR_A), "AABBCCDDEE05", "planta-que-no-existe").status_code == 404


def test_el_superadmin_registra_en_cualquier_planta(cliente, db):
    client = cliente({"sub": "root", "rol": "superadmin"})

    assert _alta(client, "AABBCCDDEE06", "planta-b").status_code == 200
    assert _en_planta(db, "planta-b") == 1


def test_un_alta_sin_planta_sigue_funcionando_como_antes(cliente):
    """Comportamiento previo, no tocado: un medidor sin planta no pertenece a ninguna organización."""
    assert _alta(cliente(OPERADOR_A), "AABBCCDDEE07", None).status_code == 200


def test_solo_lectura_sigue_recibiendo_403(cliente, db):
    r = _alta(cliente({"sub": "u9", "rol": "solo_lectura", "org": "org-a"}), "AABBCCDDEE08", "planta-a1")

    assert r.status_code == 403
    assert _en_planta(db, "planta-a1") == 0
