"""tests/unit/test_edicion_dispositivo_por_planta.py — Issue datamaq#133: PUT/PATCH /api/v1/dispositivos/{id} respeta la planta.

La ruta comprobaba la organización del medidor (y la de la planta destino) pero no la planta de origen ni las plantas
asignadas: un operador restringido a la planta a1 desactivaba o recalibraba un medidor de la planta a2. App completa con
repositorios SQLAlchemy reales sobre SQLite en memoria y la política real de acceso a plantas.
"""

from collections.abc import Callable, Iterator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.application.use_cases.gestionar_acceso_plantas import GestionarAccesoPlantasUseCase
from src.application.use_cases.gestionar_dispositivos import GestionarDispositivosUseCase
from src.domain.auth.entities import AccesoPlantaUsuario
from src.domain.telemetria.entities import Planta
from src.infrastructure.fastapi.auth_dependencies import get_acceso_plantas_use_case
from src.infrastructure.fastapi.dependencies import get_dispositivos_use_case, get_usuario_actual
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.sqlalchemy.database import get_db_session
from src.infrastructure.sqlalchemy.models import Base, DeviceModel, FacilityModel, OrganizationModel
from src.infrastructure.sqlalchemy.repositories.dispositivos_repository import MySQLDispositivosRepository

PLANTA_ORG = {"planta-a1": "org-a", "planta-a2": "org-a", "planta-b": "org-b"}
PLANTA_DE = {"dev-a1": "planta-a1", "dev-a2": "planta-a2", "dev-b": "planta-b"}
OPERADOR_A = {"sub": "u1", "rol": "operador", "org": "org-a"}
METODOS = ["patch", "put"]


@pytest.fixture()
def db() -> Iterator[Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    for org in ("org-a", "org-b"):
        session.add(OrganizationModel(id=org))
    for planta, org in PLANTA_ORG.items():
        session.add(FacilityModel(id=planta, organization_id=org, name=planta))
    for i, (dev, planta) in enumerate(PLANTA_DE.items(), start=1):
        session.add(DeviceModel(id=dev, facility_id=planta, device_uid=f"AABBCCDDEE0{i}", name=dev, esta_activo=True))
    session.commit()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def cliente(db: Session, monkeypatch) -> Callable[..., TestClient]:
    for modulo in ("device_ownership", "planta_ownership", "routes.dispositivos_router"):
        monkeypatch.setattr(f"src.infrastructure.fastapi.{modulo}.get_settings", lambda: MagicMock(AUTH_REQUIRED=True))
    monkeypatch.setattr(
        "src.infrastructure.fastapi.device_ownership._resolver_organizacion_planta",
        lambda planta_id: PLANTA_ORG.get(planta_id or ""),
    )
    plantas = [Planta(id=p, organizacion_id=o, nombre=p) for p, o in PLANTA_ORG.items()]
    repo_org = MagicMock()
    repo_org.listar_plantas.side_effect = lambda org=None: [
        p for p in plantas if org is None or p.organizacion_id == org
    ]
    # El caso de uso conoce estas plantas (no están en el YAML real): así la organización de la planta destino se
    # resuelve y lo que se prueba es la política de plantas del usuario, no una planta desconocida.
    repo_org.obtener_planta_por_id.side_effect = lambda pid: next((p for p in plantas if p.id == pid), None)
    repo_org.obtener_instalacion_medidor.return_value = None
    repo_org.obtener_nodos_unifilar.return_value = []
    repo_org.obtener_dispositivos_layout.return_value = []

    def _crear(claims: dict, plantas_asignadas: list[str] | None = None) -> TestClient:
        accesos = [
            AccesoPlantaUsuario(usuario_id="u1", planta_id=p, puede_cambiar=False) for p in plantas_asignadas or []
        ]
        acceso = GestionarAccesoPlantasUseCase(MagicMock(listar_por_usuario=lambda uid: accesos), repo_org)
        app = create_app()
        app.dependency_overrides[get_db_session] = lambda: db
        app.dependency_overrides[get_usuario_actual] = lambda: claims
        app.dependency_overrides[get_acceso_plantas_use_case] = lambda: acceso
        app.dependency_overrides[get_dispositivos_use_case] = lambda: GestionarDispositivosUseCase(
            MySQLDispositivosRepository(db), repo_org
        )
        return TestClient(app)

    return _crear


def _editar(client: TestClient, metodo: str, dispositivo: str, **cambios):
    return getattr(client, metodo)(f"/api/v1/dispositivos/{dispositivo}", json=cambios)


def _estado(db: Session, dispositivo: str) -> tuple[bool, str | None]:
    db.expire_all()
    m = db.get(DeviceModel, dispositivo)
    assert m is not None
    return m.esta_activo, m.facility_id


@pytest.mark.parametrize("metodo", METODOS)
def test_un_usuario_restringido_no_edita_un_medidor_de_otra_planta_de_su_organizacion(cliente, db, metodo):
    client = cliente(OPERADOR_A, plantas_asignadas=["planta-a1"])

    r = _editar(client, metodo, "dev-a2", esta_activo=False)

    assert r.status_code == 404
    assert _estado(db, "dev-a2") == (True, "planta-a2")


@pytest.mark.parametrize("metodo", METODOS)
def test_un_usuario_restringido_si_edita_un_medidor_de_su_planta(cliente, db, metodo):
    client = cliente(OPERADOR_A, plantas_asignadas=["planta-a1"])

    r = _editar(client, metodo, "dev-a1", nombre="renombrado")

    assert r.status_code == 200
    assert r.json()["nombre"] == "renombrado"


def test_un_usuario_restringido_no_mueve_su_medidor_a_una_planta_que_no_puede_ver(cliente, db):
    client = cliente(OPERADOR_A, plantas_asignadas=["planta-a1"])

    assert _editar(client, "patch", "dev-a1", planta_id="planta-a2").status_code == 404
    assert _editar(client, "patch", "dev-a1", planta_id="planta-b").status_code == 404
    assert _estado(db, "dev-a1") == (True, "planta-a1")


def test_un_usuario_sin_restriccion_edita_cualquier_planta_de_su_organizacion(cliente):
    assert _editar(cliente(OPERADOR_A), "patch", "dev-a2", nombre="ok").status_code == 200


def test_un_usuario_de_otra_organizacion_recibe_404(cliente, db):
    client = cliente({"sub": "u2", "rol": "operador", "org": "org-b"})

    assert _editar(client, "patch", "dev-a1", esta_activo=False).status_code == 404
    assert _estado(db, "dev-a1") == (True, "planta-a1")


def test_el_superadmin_edita_cualquier_medidor(cliente):
    client = cliente({"sub": "root", "rol": "superadmin"})

    assert _editar(client, "patch", "dev-a2", nombre="ok").status_code == 200
    assert _editar(client, "patch", "dev-b", nombre="ok").status_code == 200


def test_solo_lectura_sigue_recibiendo_403(cliente, db):
    client = cliente({"sub": "u9", "rol": "solo_lectura", "org": "org-a"})

    assert _editar(client, "patch", "dev-a1", esta_activo=False).status_code == 403
    assert _estado(db, "dev-a1") == (True, "planta-a1")
