"""tests/unit/test_auditoria_ti_aislamiento.py — Issue datamaq#128: la auditoría de cambios de TI no cruza organizaciones.

`/api/v1/admin/auditoria/cambios-ti` exigía rol admin pero no filtraba por organización: un admin de cualquier
organización leía los cambios de TI de todos los medidores, y el detalle por id (entero y consecutivo) de cualquiera.
App real, repositorio SQLAlchemy real sobre SQLite en memoria, dos organizaciones y un medidor sin planta.
"""

from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.infrastructure.fastapi.dependencies import get_usuario_actual
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.sqlalchemy.database import get_db_session
from src.infrastructure.sqlalchemy.models import (
    AuditoriaChangesTIModel,
    Base,
    DeviceModel,
    FacilityModel,
    OrganizationModel,
)

AHORA = datetime(2026, 11, 1, tzinfo=timezone.utc)
CAMBIO_A, CAMBIO_B, CAMBIO_SIN_PLANTA = 1, 2, 3
ADMIN_A = {"sub": "u-a", "rol": "admin", "org": "org-a"}


@pytest.fixture()
def db() -> Iterator[Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    for letra in ("a", "b"):
        session.add(OrganizationModel(id=f"org-{letra}"))
        session.add(FacilityModel(id=f"planta-{letra}", organization_id=f"org-{letra}", name=f"Planta {letra}"))
    session.add(DeviceModel(id="dev-a", facility_id="planta-a", device_uid="AABBCCDDEE01"))
    session.add(DeviceModel(id="dev-b", facility_id="planta-b", device_uid="AABBCCDDEE02"))
    session.add(DeviceModel(id="dev-huerfano", facility_id=None, device_uid="AABBCCDDEE03"))
    for cambio_id, dispositivo in ((CAMBIO_A, "dev-a"), (CAMBIO_B, "dev-b"), (CAMBIO_SIN_PLANTA, "dev-huerfano")):
        session.add(
            AuditoriaChangesTIModel(
                id=cambio_id,
                device_id=dispositivo,
                tipo_cambio="correccion_angular",
                valor_anterior="0",
                valor_nuevo="5",
                usuario="tec",
                timestamp=AHORA,
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
        "src.infrastructure.fastapi.routes.admin_router.get_settings", lambda: MagicMock(AUTH_REQUIRED=True)
    )

    def _crear(claims: dict) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_db_session] = lambda: db
        app.dependency_overrides[get_usuario_actual] = lambda: claims
        return TestClient(app)

    return _crear


def _ids(response) -> set[int]:
    assert response.status_code == 200
    return {r["id"] for r in response.json()["registros"]}


def test_un_admin_lista_solo_los_cambios_de_los_medidores_de_su_organizacion(cliente):
    assert _ids(cliente(ADMIN_A).get("/api/v1/admin/auditoria/cambios-ti")) == {CAMBIO_A}


def test_un_admin_no_obtiene_los_cambios_de_otra_organizacion_filtrando_por_su_dispositivo(cliente):
    respuesta = cliente(ADMIN_A).get("/api/v1/admin/auditoria/cambios-ti?dispositivo_id=dev-b")

    assert _ids(respuesta) == set()
    assert respuesta.json()["total"] == 0


def test_el_detalle_de_un_cambio_ajeno_responde_404(cliente):
    client = cliente(ADMIN_A)

    assert client.get(f"/api/v1/admin/auditoria/cambios-ti/{CAMBIO_A}").status_code == 200
    assert client.get(f"/api/v1/admin/auditoria/cambios-ti/{CAMBIO_B}").status_code == 404


def test_un_cambio_de_un_medidor_sin_planta_no_lo_ve_un_admin_de_organizacion(cliente):
    client = cliente(ADMIN_A)

    assert CAMBIO_SIN_PLANTA not in _ids(client.get("/api/v1/admin/auditoria/cambios-ti"))
    assert client.get(f"/api/v1/admin/auditoria/cambios-ti/{CAMBIO_SIN_PLANTA}").status_code == 404


def test_un_admin_sin_organizacion_no_ve_nada(cliente):
    client = cliente({"sub": "u-x", "rol": "admin"})

    assert _ids(client.get("/api/v1/admin/auditoria/cambios-ti")) == set()
    assert client.get(f"/api/v1/admin/auditoria/cambios-ti/{CAMBIO_A}").status_code == 404


def test_el_superadmin_sigue_viendo_todo(cliente):
    client = cliente({"sub": "root", "rol": "superadmin"})

    assert _ids(client.get("/api/v1/admin/auditoria/cambios-ti")) == {CAMBIO_A, CAMBIO_B, CAMBIO_SIN_PLANTA}
    assert client.get(f"/api/v1/admin/auditoria/cambios-ti/{CAMBIO_B}").status_code == 200
    assert client.get(f"/api/v1/admin/auditoria/cambios-ti/{CAMBIO_SIN_PLANTA}").status_code == 200


def test_un_rol_sin_permiso_de_admin_sigue_recibiendo_403(cliente):
    assert (
        cliente({"sub": "u", "rol": "operador", "org": "org-a"}).get("/api/v1/admin/auditoria/cambios-ti").status_code
        == 403
    )
