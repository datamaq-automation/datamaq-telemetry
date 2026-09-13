"""tests/unit/test_organizaciones_router.py — Tests unitarios para el router de organizaciones y plantas."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.organizacion_dto import (
    OrganizacionResponseDTO,
    PlantaResponseDTO,
)
from src.infrastructure.fastapi.dependencies import (
    get_dispositivos_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.server import create_app

AHORA = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


def _org_dto(**kwargs) -> OrganizacionResponseDTO:
    base = {
        "id": "org-1",
        "nombre": "Organizacion Test",
        "plan_id": "plan-pro",
        "cuit": "20-12345678-9",
        "email_contacto": "contacto@orgtest.com",
        "telefono_contacto": "+5491100000000",
        "pro_vence_en": None,
        "modo_free": "PRIVADO_BASICO",
        "creado_en": AHORA,
        "actualizado_en": AHORA,
    }
    base.update(kwargs)
    return OrganizacionResponseDTO(**base)


def _planta_dto(**kwargs) -> PlantaResponseDTO:
    base = {
        "id": "planta-1",
        "organizacion_id": "org-1",
        "nombre": "Planta Principal",
        "direccion": "Av. Libertador 1000",
        "latitud": -34.6037,
        "longitud": -58.3816,
        "creado_en": AHORA,
        "actualizado_en": AHORA,
    }
    base.update(kwargs)
    return PlantaResponseDTO(**base)


def _cliente(rol: str = "admin", org: str = "org-1") -> tuple[TestClient, MagicMock]:
    app = create_app()
    mock_use_case = MagicMock()
    app.dependency_overrides[get_dispositivos_use_case] = lambda: mock_use_case
    app.dependency_overrides[get_usuario_actual] = lambda: {
        "sub": "usuario-1",
        "rol": rol,
        "org": org,
    }
    return TestClient(app), mock_use_case


# --- LISTAR ORGANIZACIONES ---


def test_listar_organizaciones_superadmin():
    client, mock_use_case = _cliente(rol="superadmin")
    org1 = _org_dto(id="org-1", nombre="Org Alfa")
    org2 = _org_dto(id="org-2", nombre="Org Beta")
    mock_use_case.listar_organizaciones.return_value = [org1, org2]

    response = client.get("/api/v1/organizaciones")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["id"] == "org-1"
    assert data[0]["nombre"] == "Org Alfa"
    assert data[1]["id"] == "org-2"
    assert data[1]["nombre"] == "Org Beta"
    mock_use_case.listar_organizaciones.assert_called_once()


def test_listar_organizaciones_filtrado_por_tenant():
    client, mock_use_case = _cliente(rol="invitado", org="org-1")
    org1 = _org_dto(id="org-1", nombre="Org Alfa")
    org2 = _org_dto(id="org-2", nombre="Org Beta")
    mock_use_case.listar_organizaciones.return_value = [org1, org2]

    response = client.get("/api/v1/organizaciones")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "org-1"
    assert data[0]["nombre"] == "Org Alfa"
    mock_use_case.listar_organizaciones.assert_called_once()


def test_listar_organizaciones_vacio():
    client, mock_use_case = _cliente()
    mock_use_case.listar_organizaciones.return_value = []

    response = client.get("/api/v1/organizaciones")

    assert response.status_code == 200
    assert response.json() == []
    mock_use_case.listar_organizaciones.assert_called_once()


# --- ALTA POR API ELIMINADA (la estructura se declara en data/organizaciones.yml) ---


def test_post_organizaciones_ya_no_existe():
    client, mock_use_case = _cliente(rol="admin")
    response = client.post("/api/v1/organizaciones", json={"nombre": "Nueva Org"})
    assert response.status_code == 405
    assert not hasattr(mock_use_case, "crear_organizacion") or not mock_use_case.crear_organizacion.called


def test_post_plantas_ya_no_existe():
    client, mock_use_case = _cliente(rol="admin")
    response = client.post("/api/v1/plantas", json={"organizacion_id": "org-1", "nombre": "Planta"})
    assert response.status_code == 405
    assert not mock_use_case.crear_planta.called


# --- LISTAR PLANTAS ---


def test_listar_plantas_superadmin():
    client, mock_use_case = _cliente(rol="superadmin")
    planta1 = _planta_dto(id="planta-1", nombre="Planta Norte")
    planta2 = _planta_dto(id="planta-2", nombre="Planta Sur")
    mock_use_case.listar_plantas.return_value = [planta1, planta2]

    response = client.get("/api/v1/plantas")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["id"] == "planta-1"
    assert data[0]["nombre"] == "Planta Norte"
    assert data[1]["id"] == "planta-2"
    assert data[1]["nombre"] == "Planta Sur"
    mock_use_case.listar_plantas.assert_called_once_with(None)


def test_listar_plantas_usuario_regular_aislado():
    client, mock_use_case = _cliente(rol="admin", org="org-1")
    planta1 = _planta_dto(id="planta-1", organizacion_id="org-1", nombre="Planta Norte")
    mock_use_case.listar_plantas.return_value = [planta1]

    response = client.get("/api/v1/plantas")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "planta-1"
    mock_use_case.listar_plantas.assert_called_once_with("org-1")


def test_listar_plantas_con_filtro_misma_org():
    client, mock_use_case = _cliente(rol="invitado", org="org-1")
    planta1 = _planta_dto(id="planta-1", organizacion_id="org-1")
    mock_use_case.listar_plantas.return_value = [planta1]

    response = client.get("/api/v1/plantas?organizacion_id=org-1")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "planta-1"
    mock_use_case.listar_plantas.assert_called_once_with("org-1")


def test_listar_plantas_con_filtro_otra_org_fail_closed():
    client, mock_use_case = _cliente(rol="invitado", org="org-1")

    response = client.get("/api/v1/plantas?organizacion_id=org-2")

    assert response.status_code == 200
    assert response.json() == []
    mock_use_case.listar_plantas.assert_not_called()


def test_listar_plantas_vacio():
    client, mock_use_case = _cliente(rol="superadmin")
    mock_use_case.listar_plantas.return_value = []

    response = client.get("/api/v1/plantas")

    assert response.status_code == 200
    assert response.json() == []
    mock_use_case.listar_plantas.assert_called_once_with(None)
