"""tests/unit/test_billing_router.py — Tests unitarios para el router de billing (checkout + webhook MP)."""

import hashlib
import hmac
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.application.use_cases.billing.procesar_webhook_mercadopago import ResultadoWebhook
from src.domain.billing.entities import PreapprovalCreado
from src.domain.telemetria.exceptions import OrganizacionNoEncontradaError, PlanNoEncontradoError
from src.infrastructure.fastapi.dependencies import get_usuario_actual
from src.infrastructure.fastapi.dependencies_billing import (
    get_generar_checkout_use_case,
    get_procesar_webhook_mercadopago_use_case,
)
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.settings.config import get_settings

MP_SECRET = "secreto-de-test"


def _firmar(data_id: str, x_request_id: str, ts: str, secret: str = MP_SECRET) -> str:
    manifest = f"id:{data_id.lower()};request-id:{x_request_id};ts:{ts};"
    v1 = hmac.new(secret.encode("utf-8"), manifest.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"ts={ts},v1={v1}"


def _cliente(rol: str = "admin", con_org: bool = True) -> tuple[TestClient, dict[str, MagicMock]]:
    get_settings.cache_clear()
    app = create_app()
    mocks = {"checkout": MagicMock(), "webhook": MagicMock()}
    app.dependency_overrides[get_generar_checkout_use_case] = lambda: mocks["checkout"]
    app.dependency_overrides[get_procesar_webhook_mercadopago_use_case] = lambda: mocks["webhook"]
    claims = {"sub": "usr-123", "rol": rol}
    if con_org:
        claims["org"] = "org-001"
    app.dependency_overrides[get_usuario_actual] = lambda: claims
    return TestClient(app), mocks


# ============================================================================
# POST /api/v1/suscripciones/checkout
# ============================================================================


def test_checkout_exitoso_devuelve_init_point():
    client, mocks = _cliente(rol="admin")
    mocks["checkout"].ejecutar.return_value = PreapprovalCreado(id="preap-1", init_point="https://mp.example/x")

    response = client.post("/api/v1/suscripciones/checkout", json={"plan_id": "plan-pro"})

    assert response.status_code == 200
    mocks["checkout"].ejecutar.assert_called_once_with("org-001", "plan-pro")
    data = response.json()
    assert data["preapproval_id"] == "preap-1"
    assert data["init_point"] == "https://mp.example/x"


def test_checkout_rol_operador_rechazado_403():
    client, mocks = _cliente(rol="operador")

    response = client.post("/api/v1/suscripciones/checkout", json={"plan_id": "plan-pro"})

    assert response.status_code == 403
    mocks["checkout"].ejecutar.assert_not_called()


def test_checkout_no_autenticado_rechazado_401():
    app = create_app()

    def _raise_unauthorized():
        raise HTTPException(status_code=401, detail="Token no proporcionado")

    app.dependency_overrides[get_usuario_actual] = _raise_unauthorized
    client = TestClient(app)

    response = client.post("/api/v1/suscripciones/checkout", json={"plan_id": "plan-pro"})

    assert response.status_code == 401


def test_checkout_usuario_sin_organizacion_422():
    client, mocks = _cliente(rol="admin", con_org=False)

    response = client.post("/api/v1/suscripciones/checkout", json={"plan_id": "plan-pro"})

    assert response.status_code == 422
    mocks["checkout"].ejecutar.assert_not_called()


def test_checkout_plan_inexistente_mapeado_a_422():
    client, mocks = _cliente(rol="admin")
    mocks["checkout"].ejecutar.side_effect = PlanNoEncontradoError("Plan 'x' no existe.")

    response = client.post("/api/v1/suscripciones/checkout", json={"plan_id": "x"})

    assert response.status_code == 422
    assert response.json()["detail"] == "Plan 'x' no existe."


def test_checkout_organizacion_inexistente_mapeado_a_422():
    client, mocks = _cliente(rol="admin")
    mocks["checkout"].ejecutar.side_effect = OrganizacionNoEncontradaError("Organización 'x' no existe.")

    response = client.post("/api/v1/suscripciones/checkout", json={"plan_id": "plan-pro"})

    assert response.status_code == 422


# ============================================================================
# POST /api/v1/webhooks/mercadopago
# ============================================================================


def test_webhook_firma_valida_procesa_evento():
    client, mocks = _cliente()
    mocks["webhook"].ejecutar.return_value = ResultadoWebhook(procesado=True, accion="activado")

    with patch("src.infrastructure.fastapi.routes.billing_router.get_settings") as mock_settings:
        mock_settings.return_value.MP_WEBHOOK_SECRET = MP_SECRET
        x_sig = _firmar("preap-1", "req-1", "1700000000")
        response = client.post(
            "/api/v1/webhooks/mercadopago?data.id=preap-1&id=evt-1",
            headers={"x-signature": x_sig, "x-request-id": "req-1"},
        )

    assert response.status_code == 200
    assert response.json()["accion"] == "activado"
    mocks["webhook"].ejecutar.assert_called_once_with(event_id="evt-1", preapproval_id="preap-1")


def test_webhook_firma_invalida_rechazado_401():
    client, mocks = _cliente()

    with patch("src.infrastructure.fastapi.routes.billing_router.get_settings") as mock_settings:
        mock_settings.return_value.MP_WEBHOOK_SECRET = MP_SECRET
        x_sig = _firmar("preap-1", "req-1", "1700000000", secret="otro-secreto")
        response = client.post(
            "/api/v1/webhooks/mercadopago?data.id=preap-1&id=evt-1",
            headers={"x-signature": x_sig, "x-request-id": "req-1"},
        )

    assert response.status_code == 401
    mocks["webhook"].ejecutar.assert_not_called()


def test_webhook_sin_headers_de_firma_400():
    client, mocks = _cliente()

    response = client.post("/api/v1/webhooks/mercadopago?data.id=preap-1&id=evt-1")

    assert response.status_code == 400
    assert response.json()["detail"] == "Solicitud sin firma válida."
    assert "x-signature" not in response.text
    mocks["webhook"].ejecutar.assert_not_called()


def test_webhook_sin_data_id_400():
    client, mocks = _cliente()

    response = client.post(
        "/api/v1/webhooks/mercadopago", headers={"x-signature": "ts=1,v1=x", "x-request-id": "req-1"}
    )

    assert response.status_code == 400
    mocks["webhook"].ejecutar.assert_not_called()


def test_webhook_no_requiere_autenticacion_de_usuario():
    """A diferencia de /checkout, Mercado Pago no manda un JWT nuestro — la
    identidad la da la firma, no get_usuario_actual."""
    app = create_app()
    mocks = {"webhook": MagicMock()}
    mocks["webhook"].ejecutar.return_value = ResultadoWebhook(procesado=True, accion="activado")
    app.dependency_overrides[get_procesar_webhook_mercadopago_use_case] = lambda: mocks["webhook"]

    def _raise_unauthorized():
        raise HTTPException(status_code=401, detail="Token no proporcionado")

    app.dependency_overrides[get_usuario_actual] = _raise_unauthorized
    client = TestClient(app)

    with patch("src.infrastructure.fastapi.routes.billing_router.get_settings") as mock_settings:
        mock_settings.return_value.MP_WEBHOOK_SECRET = MP_SECRET
        x_sig = _firmar("preap-1", "req-1", "1700000000")
        response = client.post(
            "/api/v1/webhooks/mercadopago?data.id=preap-1&id=evt-1",
            headers={"x-signature": x_sig, "x-request-id": "req-1"},
        )

    assert response.status_code == 200
