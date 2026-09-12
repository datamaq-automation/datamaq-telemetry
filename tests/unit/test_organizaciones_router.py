"""tests/unit/test_organizaciones_router.py — Tests unitarios para el router de organizaciones y plantas."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.organizacion_dto import (
    OrganizacionResponseDTO,
    PlantaResponseDTO,
)
from src.domain.telemetria.exceptions import (
    DominioTelemetriaException,
    PlantaNoEncontradaError,
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


def _cliente(rol: str = "admin") -> tuple[TestClient, MagicMock]:
    app = create_app()
    mock_use_case = MagicMock()
    app.dependency_overrides[get_dispositivos_use_case] = lambda: mock_use_case
    app.dependency_overrides[get_usuario_actual] = lambda: {
        "sub": "usuario-1",
        "rol": rol,
        "org": "org-1",
    }
    return TestClient(app), mock_use_case


# --- LISTAR ORGANIZACIONES ---


def test_listar_organizaciones_exitoso():
    client, mock_use_case = _cliente()
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


def test_listar_organizaciones_vacio():
    client, mock_use_case = _cliente()
    mock_use_case.listar_organizaciones.return_value = []

    response = client.get("/api/v1/organizaciones")

    assert response.status_code == 200
    assert response.json() == []
    mock_use_case.listar_organizaciones.assert_called_once()


# --- CREAR ORGANIZACION ---


def test_crear_organizacion_exitoso():
    client, mock_use_case = _cliente()
    mock_use_case.crear_organizacion.return_value = _org_dto(
        id="org-nueva",
        nombre="Nueva Organizacion S.A.",
        cuit="30-98765432-1",
    )

    payload = {
        "nombre": "Nueva Organizacion S.A.",
        "cuit": "30-98765432-1",
        "plan_id": "plan-basic",
        "email_contacto": "info@nuevaorg.com",
        "telefono_contacto": "+541122334455",
        "modo_free": "PRIVADO_BASICO",
    }
    response = client.post("/api/v1/organizaciones", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "org-nueva"
    assert data["nombre"] == "Nueva Organizacion S.A."
    assert data["cuit"] == "30-98765432-1"
    mock_use_case.crear_organizacion.assert_called_once()
    dto_llamado = mock_use_case.crear_organizacion.call_args[0][0]
    assert dto_llamado.nombre == "Nueva Organizacion S.A."
    assert dto_llamado.cuit == "30-98765432-1"


def test_crear_organizacion_rol_invitado_rechazado_403():
    client, mock_use_case = _cliente(rol="invitado")

    payload = {"nombre": "Org No Permitida"}
    response = client.post("/api/v1/organizaciones", json=payload)

    assert response.status_code == 403
    assert response.json()["detail"] == "forbidden"
    mock_use_case.crear_organizacion.assert_not_called()


def test_crear_organizacion_rol_invitado_global_rechazado_403():
    client, mock_use_case = _cliente(rol="invitado_global")

    payload = {"nombre": "Org No Permitida"}
    response = client.post("/api/v1/organizaciones", json=payload)

    assert response.status_code == 403
    assert response.json()["detail"] == "forbidden"
    mock_use_case.crear_organizacion.assert_not_called()


def test_crear_organizacion_error_dominio_422():
    client, mock_use_case = _cliente()
    mock_use_case.crear_organizacion.side_effect = DominioTelemetriaException("Organizacion duplicada")

    payload = {"nombre": "Org Duplicada"}
    response = client.post("/api/v1/organizaciones", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"] == "Organizacion duplicada"


def test_crear_organizacion_error_inesperado_500():
    client, mock_use_case = _cliente()
    mock_use_case.crear_organizacion.side_effect = RuntimeError("Fallo de conexion a base de datos")

    payload = {"nombre": "Org Inesperada"}
    response = client.post("/api/v1/organizaciones", json=payload)

    assert response.status_code == 500
    assert response.json()["detail"] == "Ocurrió un error interno en el servidor"


def test_crear_organizacion_payload_invalido_422():
    client, mock_use_case = _cliente()

    # 'nombre' es campo requerido
    response = client.post("/api/v1/organizaciones", json={})

    assert response.status_code == 422
    mock_use_case.crear_organizacion.assert_not_called()


# --- LISTAR PLANTAS ---


def test_listar_plantas_sin_filtro():
    client, mock_use_case = _cliente()
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


def test_listar_plantas_con_filtro_organizacion_id():
    client, mock_use_case = _cliente()
    planta1 = _planta_dto(id="planta-1", organizacion_id="org-especifica")
    mock_use_case.listar_plantas.return_value = [planta1]

    response = client.get("/api/v1/plantas?organizacion_id=org-especifica")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "planta-1"
    assert data[0]["organizacion_id"] == "org-especifica"
    mock_use_case.listar_plantas.assert_called_once_with("org-especifica")


def test_listar_plantas_vacio():
    client, mock_use_case = _cliente()
    mock_use_case.listar_plantas.return_value = []

    response = client.get("/api/v1/plantas")

    assert response.status_code == 200
    assert response.json() == []
    mock_use_case.listar_plantas.assert_called_once_with(None)


# --- CREAR PLANTA ---


def test_crear_planta_exitoso():
    client, mock_use_case = _cliente()
    mock_use_case.crear_planta.return_value = _planta_dto(
        id="planta-nueva",
        organizacion_id="org-1",
        nombre="Planta Centro",
        direccion="Ruta 9 Km 200",
        latitud=-32.5,
        longitud=-60.5,
    )

    payload = {
        "organizacion_id": "org-1",
        "nombre": "Planta Centro",
        "direccion": "Ruta 9 Km 200",
        "latitud": -32.5,
        "longitud": -60.5,
    }
    response = client.post("/api/v1/plantas", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "planta-nueva"
    assert data["organizacion_id"] == "org-1"
    assert data["nombre"] == "Planta Centro"
    assert data["direccion"] == "Ruta 9 Km 200"
    assert data["latitud"] == -32.5
    assert data["longitud"] == -60.5
    mock_use_case.crear_planta.assert_called_once()
    dto_llamado = mock_use_case.crear_planta.call_args[0][0]
    assert dto_llamado.nombre == "Planta Centro"
    assert dto_llamado.organizacion_id == "org-1"


def test_crear_planta_rol_invitado_rechazado_403():
    client, mock_use_case = _cliente(rol="invitado")

    payload = {
        "organizacion_id": "org-1",
        "nombre": "Planta No Permitida",
    }
    response = client.post("/api/v1/plantas", json=payload)

    assert response.status_code == 403
    assert response.json()["detail"] == "forbidden"
    mock_use_case.crear_planta.assert_not_called()


def test_crear_planta_rol_invitado_global_rechazado_403():
    client, mock_use_case = _cliente(rol="invitado_global")

    payload = {
        "organizacion_id": "org-1",
        "nombre": "Planta No Permitida",
    }
    response = client.post("/api/v1/plantas", json=payload)

    assert response.status_code == 403
    assert response.json()["detail"] == "forbidden"
    mock_use_case.crear_planta.assert_not_called()


def test_crear_planta_error_dominio_422():
    client, mock_use_case = _cliente()
    mock_use_case.crear_planta.side_effect = DominioTelemetriaException("Planta duplicada")

    payload = {
        "organizacion_id": "org-1",
        "nombre": "Planta Duplicada",
    }
    response = client.post("/api/v1/plantas", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"] == "Planta duplicada"


def test_crear_planta_no_encontrada_404():
    client, mock_use_case = _cliente()
    mock_use_case.crear_planta.side_effect = PlantaNoEncontradaError("Planta padre no encontrada")

    payload = {
        "organizacion_id": "org-1",
        "nombre": "Planta Inexistente",
    }
    response = client.post("/api/v1/plantas", json=payload)

    assert response.status_code == 404
    assert response.json()["detail"] == "Planta padre no encontrada"


def test_crear_planta_error_inesperado_500():
    client, mock_use_case = _cliente()
    mock_use_case.crear_planta.side_effect = RuntimeError("Error imprevisto")

    payload = {
        "organizacion_id": "org-1",
        "nombre": "Planta Inesperada",
    }
    response = client.post("/api/v1/plantas", json=payload)

    assert response.status_code == 500
    assert response.json()["detail"] == "Ocurrió un error interno en el servidor"


def test_crear_planta_payload_invalido_422():
    client, mock_use_case = _cliente()

    # Faltan campos requeridos ('organizacion_id', 'nombre')
    response = client.post("/api/v1/plantas", json={})

    assert response.status_code == 422
    mock_use_case.crear_planta.assert_not_called()
