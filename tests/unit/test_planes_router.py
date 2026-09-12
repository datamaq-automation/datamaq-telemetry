"""tests/unit/test_planes_router.py — Tests unitarios para el router de planes de telemetría."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.application.dtos.plan_dto import PlanResponseDTO
from src.domain.telemetria.exceptions import DominioTelemetriaException
from src.domain.telemetria.value_objects import VisibilidadPlan
from src.infrastructure.fastapi.dependencies import (
    get_planes_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.server import create_app

AHORA = datetime(2026, 9, 12, 10, 0, 0, tzinfo=timezone.utc)


def _plan_response_dto(**kwargs) -> PlanResponseDTO:
    base = {
        "id": "plan-001",
        "nombre": "Plan Industrial",
        "descripcion": "Telemetría avanzada para líneas de producción",
        "precio_mensual_ars": Decimal("25000.00"),
        "visibilidad": VisibilidadPlan.PUBLICO,
        "retencion_dias": 30,
        "granularidad_minutos": 1,
        "max_dispositivos": 5,
        "canales_notificacion": ["email", "telegram"],
        "creado_en": AHORA,
        "actualizado_en": AHORA,
    }
    base.update(kwargs)
    return PlanResponseDTO(**base)


def _payload_crear_plan(**kwargs) -> dict:
    base = {
        "nombre": "Plan Industrial",
        "descripcion": "Telemetría avanzada para líneas de producción",
        "precio_mensual_ars": 25000.00,
        "visibilidad": "PUBLICO",
        "retencion_dias": 30,
        "granularidad_minutos": 1,
        "max_dispositivos": 5,
        "canales_notificacion": ["email", "telegram"],
    }
    base.update(kwargs)
    return base


def _cliente(rol: str = "admin") -> tuple[TestClient, dict[str, MagicMock]]:
    app = create_app()
    mocks = {
        "planes": MagicMock(),
    }
    app.dependency_overrides[get_planes_use_case] = lambda: mocks["planes"]
    app.dependency_overrides[get_usuario_actual] = lambda: {
        "sub": "usr-123",
        "rol": rol,
        "org": "org-001",
    }
    return TestClient(app), mocks


# ============================================================================
# GET /api/v1/planes — Consulta de catálogo de planes
# ============================================================================


def test_listar_planes_exitoso_default_params():
    client, mocks = _cliente()
    mocks["planes"].listar_catalogo.return_value = [_plan_response_dto()]

    response = client.get("/api/v1/planes")

    assert response.status_code == 200
    mocks["planes"].listar_catalogo.assert_called_once_with(solo_publicos=False)
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "plan-001"
    assert data[0]["nombre"] == "Plan Industrial"
    assert data[0]["descripcion"] == "Telemetría avanzada para líneas de producción"
    assert Decimal(str(data[0]["precio_mensual_ars"])) == Decimal("25000.00")
    assert data[0]["visibilidad"] == "PUBLICO"
    assert data[0]["retencion_dias"] == 30
    assert data[0]["granularidad_minutos"] == 1
    assert data[0]["max_dispositivos"] == 5
    assert data[0]["canales_notificacion"] == ["email", "telegram"]


def test_listar_planes_solo_publicos_true():
    client, mocks = _cliente()
    mocks["planes"].listar_catalogo.return_value = [_plan_response_dto()]

    response = client.get("/api/v1/planes?solo_publicos=true")

    assert response.status_code == 200
    mocks["planes"].listar_catalogo.assert_called_once_with(solo_publicos=True)


def test_listar_planes_solo_publicos_false():
    client, mocks = _cliente()
    mocks["planes"].listar_catalogo.return_value = [_plan_response_dto()]

    response = client.get("/api/v1/planes?solo_publicos=false")

    assert response.status_code == 200
    mocks["planes"].listar_catalogo.assert_called_once_with(solo_publicos=False)


def test_listar_planes_catalogo_vacio():
    client, mocks = _cliente()
    mocks["planes"].listar_catalogo.return_value = []

    response = client.get("/api/v1/planes")

    assert response.status_code == 200
    assert response.json() == []
    mocks["planes"].listar_catalogo.assert_called_once_with(solo_publicos=False)


def test_listar_planes_no_autenticado_rechazado_401():
    app = create_app()

    def _raise_unauthorized():
        raise HTTPException(status_code=401, detail="Token no proporcionado")

    app.dependency_overrides[get_usuario_actual] = _raise_unauthorized
    client = TestClient(app)

    response = client.get("/api/v1/planes")

    assert response.status_code == 401
    assert response.json()["detail"] == "Token no proporcionado"


# ============================================================================
# POST /api/v1/planes — Creación de plan
# ============================================================================


def test_crear_plan_exitoso():
    client, mocks = _cliente(rol="admin")
    mocks["planes"].crear_plan.return_value = _plan_response_dto()

    payload = _payload_crear_plan()
    response = client.post("/api/v1/planes", json=payload)

    assert response.status_code == 200
    mocks["planes"].crear_plan.assert_called_once()
    dto_llamado = mocks["planes"].crear_plan.call_args[0][0]
    assert dto_llamado.nombre == "Plan Industrial"
    assert dto_llamado.descripcion == "Telemetría avanzada para líneas de producción"
    assert dto_llamado.precio_mensual_ars == Decimal("25000.00")
    assert dto_llamado.visibilidad == VisibilidadPlan.PUBLICO
    assert dto_llamado.retencion_dias == 30
    assert dto_llamado.granularidad_minutos == 1
    assert dto_llamado.max_dispositivos == 5
    assert dto_llamado.canales_notificacion == ["email", "telegram"]

    data = response.json()
    assert data["id"] == "plan-001"
    assert data["nombre"] == "Plan Industrial"
    assert data["retencion_dias"] == 30


def test_crear_plan_rol_invitado_rechazado_403():
    client, mocks = _cliente(rol="invitado")

    payload = _payload_crear_plan()
    response = client.post("/api/v1/planes", json=payload)

    assert response.status_code == 403
    assert response.json()["detail"] == "forbidden"
    mocks["planes"].crear_plan.assert_not_called()


def test_crear_plan_rol_invitado_global_rechazado_403():
    client, mocks = _cliente(rol="invitado_global")

    payload = _payload_crear_plan()
    response = client.post("/api/v1/planes", json=payload)

    assert response.status_code == 403
    assert response.json()["detail"] == "forbidden"
    mocks["planes"].crear_plan.assert_not_called()


def test_crear_plan_no_autenticado_rechazado_401():
    app = create_app()

    def _raise_unauthorized():
        raise HTTPException(status_code=401, detail="Token no proporcionado")

    app.dependency_overrides[get_usuario_actual] = _raise_unauthorized
    client = TestClient(app)

    payload = _payload_crear_plan()
    response = client.post("/api/v1/planes", json=payload)

    assert response.status_code == 401
    assert response.json()["detail"] == "Token no proporcionado"


def test_crear_plan_payload_invalido_faltan_campos_422():
    client, mocks = _cliente()

    payload = {"nombre": "Plan Incompleto"}
    response = client.post("/api/v1/planes", json=payload)

    assert response.status_code == 422
    mocks["planes"].crear_plan.assert_not_called()


def test_crear_plan_payload_invalido_visibilidad_invalida_422():
    client, mocks = _cliente()

    payload = _payload_crear_plan(visibilidad="DESCONOCIDO")
    response = client.post("/api/v1/planes", json=payload)

    assert response.status_code == 422
    mocks["planes"].crear_plan.assert_not_called()


def test_crear_plan_error_de_dominio_mapeado_a_422():
    client, mocks = _cliente()
    mocks["planes"].crear_plan.side_effect = DominioTelemetriaException("Plan inválido por regla de negocio")

    payload = _payload_crear_plan()
    response = client.post("/api/v1/planes", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"] == "Plan inválido por regla de negocio"


def test_crear_plan_error_inesperado_mapeado_a_500():
    client, mocks = _cliente()
    mocks["planes"].crear_plan.side_effect = RuntimeError("Error inesperado en base de datos")

    payload = _payload_crear_plan()
    response = client.post("/api/v1/planes", json=payload)

    assert response.status_code == 500
    assert response.json()["detail"] == "Ocurrió un error interno en el servidor"
