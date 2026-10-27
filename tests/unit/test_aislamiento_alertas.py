"""tests/unit/test_aislamiento_alertas.py — `/api/v1/alertas` no expone ni resuelve alertas de otra organización (IDOR).

App completa con repositorios SQLAlchemy reales sobre SQLite en memoria: org A y org B, cada una con
planta, medidor y una alerta abierta.
"""

from collections.abc import Callable, Iterator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.application.use_cases.gestionar_acceso_plantas import GestionarAccesoPlantasUseCase
from src.domain.telemetria.entities import Planta
from src.infrastructure.fastapi.auth_dependencies import get_acceso_plantas_use_case
from src.infrastructure.fastapi.dependencies import get_usuario_actual
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.sqlalchemy.database import get_db_session
from src.infrastructure.sqlalchemy.models import (
    Base,
    DeviceAlertModel,
    DeviceModel,
    FacilityModel,
    OrganizationModel,
)

ALERTA_A, ALERTA_B = 1, 2


@pytest.fixture()
def db() -> Iterator[Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    for alerta_id, letra in ((ALERTA_A, "a"), (ALERTA_B, "b")):
        session.add(OrganizationModel(id=f"org-{letra}"))
        session.add(FacilityModel(id=f"planta-{letra}", organization_id=f"org-{letra}", name=f"Planta {letra}"))
        session.add(DeviceModel(id=f"dev-{letra}", facility_id=f"planta-{letra}", device_uid=f"AABBCCDDEE0{alerta_id}"))
        session.add(
            DeviceAlertModel(
                id=alerta_id,
                device_id=f"dev-{letra}",
                alert_type=f"ALERTA_{letra.upper()}",
                severity="WARNING",
                message="x",
            )
        )
    session.commit()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def cliente(db: Session, monkeypatch) -> Callable[[dict], TestClient]:
    monkeypatch.setattr(
        "src.infrastructure.fastapi.device_ownership.get_settings", lambda: MagicMock(AUTH_REQUIRED=True)
    )
    # La organización de una planta se resuelve contra el YAML; acá, contra las plantas del fixture.
    monkeypatch.setattr(
        "src.infrastructure.fastapi.device_ownership._resolver_organizacion_planta",
        lambda planta_id: {"planta-a": "org-a", "planta-b": "org-b"}.get(planta_id or ""),
    )

    plantas_fixture = [
        Planta(id="planta-a", organizacion_id="org-a", nombre="Planta A"),
        Planta(id="planta-b", organizacion_id="org-b", nombre="Planta B"),
    ]
    repo_org_mock = MagicMock()
    repo_org_mock.listar_plantas.side_effect = lambda org=None: [
        p for p in plantas_fixture if org is None or p.organizacion_id == org
    ]
    repo_org_mock.obtener_planta_por_id.side_effect = lambda pid: next(
        (p for p in plantas_fixture if p.id == pid), None
    )
    acceso_mock = GestionarAccesoPlantasUseCase(MagicMock(listar_por_usuario=lambda uid: []), repo_org_mock)

    def _crear(claims: dict) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_db_session] = lambda: db
        app.dependency_overrides[get_usuario_actual] = lambda: claims
        app.dependency_overrides[get_acceso_plantas_use_case] = lambda: acceso_mock
        return TestClient(app)

    return _crear


USUARIO_A = {"sub": "u-a", "rol": "operador", "org": "org-a"}


def _tipos(response) -> set[str]:
    assert response.status_code == 200
    return {a["tipo_alerta"] for a in response.json()}


def test_listado_solo_trae_alertas_de_la_organizacion_del_usuario(cliente):
    client = cliente(USUARIO_A)
    assert _tipos(client.get("/api/v1/alertas")) == {"ALERTA_A"}
    assert _tipos(client.get("/api/v1/alertas?device_id=dev-b")) == set()


@pytest.mark.parametrize("rol", ["superadmin"])
def test_roles_globales_listan_todas(cliente, rol):
    assert _tipos(cliente({"sub": "u-g", "rol": rol}).get("/api/v1/alertas")) == {"ALERTA_A", "ALERTA_B"}


def test_listado_filtrado_por_planta_id_aisla_alertas_de_otra_planta(cliente):
    client_global = cliente({"sub": "u-g", "rol": "superadmin"})
    assert _tipos(client_global.get("/api/v1/alertas?planta_id=planta-a")) == {"ALERTA_A"}
    assert _tipos(client_global.get("/api/v1/alertas?planta_id=planta-b")) == {"ALERTA_B"}


def test_usuario_sin_organizacion_no_lista_nada(cliente):
    assert _tipos(cliente({"sub": "u-x", "rol": "operador"}).get("/api/v1/alertas")) == set()


@pytest.mark.parametrize("metodo", ["post", "patch"])
def test_no_puede_resolver_alerta_de_otra_organizacion(cliente, db: Session, metodo):
    response = getattr(cliente(USUARIO_A), metodo)(f"/api/v1/alertas/{ALERTA_B}/resolver", json={})

    assert response.status_code == 404
    assert response.json()["detail"] == "alerta_no_encontrada"
    db.expire_all()
    assert db.get(DeviceAlertModel, ALERTA_B).is_resolved is False


def test_resuelve_su_propia_alerta(cliente, db: Session):
    response = cliente(USUARIO_A).post(f"/api/v1/alertas/{ALERTA_A}/resolver", json={"observaciones": "ok"})

    assert response.status_code == 200
    db.expire_all()
    assert db.get(DeviceAlertModel, ALERTA_A).is_resolved is True


def test_alerta_inexistente_responde_igual_que_la_ajena(cliente):
    response = cliente(USUARIO_A).post("/api/v1/alertas/999/resolver", json={})
    assert response.status_code == 404
    assert response.json()["detail"] == "alerta_no_encontrada"
