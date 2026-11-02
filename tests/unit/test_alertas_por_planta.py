"""tests/unit/test_alertas_por_planta.py — Issue datamaq#137: las alertas respetan las plantas permitidas del usuario.

`GET /api/v1/alertas` sin `planta_id` devolvía las alertas de TODAS las plantas de la organización a un usuario restringido
por user_facility_access a una sola, y `verificar_propiedad_alerta` comprobaba solo la organización. App completa con
repositorios SQLAlchemy reales sobre SQLite en memoria y la política real de acceso a plantas.
"""

from collections.abc import Callable, Iterator
from datetime import datetime, timedelta, timezone
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
from src.infrastructure.sqlalchemy.models import (
    Base,
    DeviceAlertModel,
    DeviceModel,
    FacilityModel,
    OrganizationModel,
)

PLANTA_ORG = {"planta-a1": "org-a", "planta-a2": "org-a", "planta-b": "org-b"}
BASE = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
OPERADOR_A = {"sub": "u1", "rol": "operador", "org": "org-a"}


def _tipos(response) -> set[str]:
    assert response.status_code == 200
    return {a["tipo_alerta"] for a in response.json()}


@pytest.fixture()
def db() -> Iterator[Session]:
    """Tres plantas (dos de org-a, una de org-b), un medidor por planta. La planta a2 tiene 5 alertas MÁS NUEVAS que la
    única de a1: si el filtro por planta se aplicara después del límite, un usuario de a1 con límite 1 vería una lista vacía."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    for org in ("org-a", "org-b"):
        session.add(OrganizationModel(id=org))
    for i, (planta, org) in enumerate(PLANTA_ORG.items(), start=1):
        session.add(FacilityModel(id=planta, organization_id=org, name=planta))
        session.add(DeviceModel(id=f"dev-{planta}", facility_id=planta, device_uid=f"AABBCCDDEE0{i}"))
    session.add(
        DeviceAlertModel(
            id=1, device_id="dev-planta-a1", alert_type="A1", severity="WARNING", message="x", triggered_at=BASE
        )
    )
    for n in range(5):
        session.add(
            DeviceAlertModel(
                id=10 + n,
                device_id="dev-planta-a2",
                alert_type=f"A2-{n}",
                severity="WARNING",
                message="x",
                triggered_at=BASE + timedelta(minutes=1 + n),
            )
        )
    session.add(
        DeviceAlertModel(
            id=99, device_id="dev-planta-b", alert_type="B", severity="WARNING", message="x", triggered_at=BASE
        )
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def cliente(db: Session, monkeypatch) -> Callable[..., TestClient]:
    for modulo in ("device_ownership", "planta_ownership"):
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


A2 = {f"A2-{n}" for n in range(5)}


def test_un_usuario_restringido_a_una_planta_solo_ve_las_alertas_de_esa_planta(cliente):
    assert _tipos(cliente(OPERADOR_A, ["planta-a1"]).get("/api/v1/alertas")) == {"A1"}


def test_un_usuario_restringido_no_ve_alertas_de_otra_planta_filtrando_por_su_dispositivo(cliente):
    respuesta = cliente(OPERADOR_A, ["planta-a1"]).get("/api/v1/alertas?device_id=dev-planta-a2")

    assert _tipos(respuesta) == set()


def test_pedir_la_planta_no_asignada_sigue_siendo_404(cliente):
    assert cliente(OPERADOR_A, ["planta-a1"]).get("/api/v1/alertas?planta_id=planta-a2").status_code == 404


def test_el_limite_se_aplica_despues_del_filtro_por_planta(cliente):
    """Las 5 alertas de a2 son más nuevas: con limit=1 el usuario de a1 tiene que recibir igual la suya."""
    assert _tipos(cliente(OPERADOR_A, ["planta-a1"]).get("/api/v1/alertas?limit=1")) == {"A1"}


def test_un_usuario_con_varias_plantas_ve_la_union_de_las_suyas(cliente):
    client = cliente(OPERADOR_A, ["planta-a1", "planta-a2"])

    assert _tipos(client.get("/api/v1/alertas")) == {"A1"} | A2


def test_un_usuario_sin_restriccion_ve_todas_las_plantas_de_su_organizacion(cliente):
    assert _tipos(cliente(OPERADOR_A).get("/api/v1/alertas")) == {"A1"} | A2


def test_pedir_una_planta_propia_trae_solo_esa(cliente):
    client = cliente(OPERADOR_A, ["planta-a1", "planta-a2"])

    assert _tipos(client.get("/api/v1/alertas?planta_id=planta-a1")) == {"A1"}


def test_el_superadmin_ve_todo(cliente):
    assert _tipos(cliente({"sub": "root", "rol": "superadmin"}).get("/api/v1/alertas?limit=500")) == {"A1", "B"} | A2


def test_un_usuario_sin_organizacion_no_ve_nada(cliente):
    assert _tipos(cliente({"sub": "u9", "rol": "operador"}).get("/api/v1/alertas")) == set()


def test_un_usuario_restringido_no_resuelve_una_alerta_de_otra_planta(cliente, db):
    r = cliente(OPERADOR_A, ["planta-a1"]).post("/api/v1/alertas/10/resolver")

    assert r.status_code == 404
    db.expire_all()
    assert db.get(DeviceAlertModel, 10).is_resolved is False


def test_un_usuario_restringido_si_resuelve_una_alerta_de_su_planta(cliente):
    assert cliente(OPERADOR_A, ["planta-a1"]).post("/api/v1/alertas/1/resolver").status_code == 200
