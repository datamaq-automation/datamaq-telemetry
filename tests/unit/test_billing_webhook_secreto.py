"""tests/unit/test_billing_webhook_secreto.py — El webhook de MP no procesa nada sin secreto usable (Issue #45).

Billing activo + MP_WEBHOOK_SECRET vacío → 503 genérico, sin ejecutar el caso de uso. Con secreto presente la
firma HMAC decide: válida → procesa, inválida → 401.
"""

import hashlib
import hmac
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.application.use_cases.billing.procesar_webhook_mercadopago import ResultadoWebhook
from src.infrastructure.fastapi.dependencies_billing import get_procesar_webhook_mercadopago_use_case
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.settings.config import Settings

MP_SECRET = "secreto-mp-de-test"
URL = "/api/v1/webhooks/mercadopago?data.id=preap-1&id=evt-1"


def _firmar(data_id: str, x_request_id: str, ts: str, secret: str) -> str:
    manifest = f"id:{data_id.lower()};request-id:{x_request_id};ts:{ts};"
    v1 = hmac.new(secret.encode("utf-8"), manifest.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"ts={ts},v1={v1}"


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, APP_ENV="development", DEBUG=True, BILLING_HABILITADO=True, **overrides)


def _cliente() -> tuple[TestClient, MagicMock]:
    app = create_app()
    webhook = MagicMock()
    webhook.ejecutar.return_value = ResultadoWebhook(procesado=True, accion="activado")
    app.dependency_overrides[get_procesar_webhook_mercadopago_use_case] = lambda: webhook
    return TestClient(app), webhook


def _post_firmado(client: TestClient, secret_firma: str):
    headers = {"x-signature": _firmar("preap-1", "req-1", "1700000000", secret_firma), "x-request-id": "req-1"}
    return client.post(URL, headers=headers)


def test_secreto_vacio_con_billing_activo_responde_503_y_no_ejecuta():
    settings = _settings(MP_WEBHOOK_SECRET="")
    client, webhook = _cliente()

    with patch("src.infrastructure.fastapi.routes.billing_router.get_settings", return_value=settings):
        response = _post_firmado(client, secret_firma="")

    assert response.status_code == 503
    assert "MP_WEBHOOK_SECRET" not in response.text
    webhook.ejecutar.assert_not_called()


def test_secreto_vacio_no_acepta_firma_hecha_con_clave_vacia():
    """El ataque: firmar con clave vacía. Debe fallar cerrado (503), no validar la firma."""
    settings = _settings(MP_WEBHOOK_SECRET="")
    client, webhook = _cliente()

    with patch("src.infrastructure.fastapi.routes.billing_router.get_settings", return_value=settings):
        response = _post_firmado(client, secret_firma="")

    assert response.status_code != 200
    webhook.ejecutar.assert_not_called()


def test_secreto_presente_firma_valida_procesa_evento():
    settings = _settings(MP_WEBHOOK_SECRET=MP_SECRET)
    client, webhook = _cliente()

    with patch("src.infrastructure.fastapi.routes.billing_router.get_settings", return_value=settings):
        response = _post_firmado(client, secret_firma=MP_SECRET)

    assert response.status_code == 200
    assert response.json()["accion"] == "activado"
    webhook.ejecutar.assert_called_once_with(event_id="evt-1", preapproval_id="preap-1")


def test_secreto_presente_firma_invalida_responde_401():
    settings = _settings(MP_WEBHOOK_SECRET=MP_SECRET)
    client, webhook = _cliente()

    with patch("src.infrastructure.fastapi.routes.billing_router.get_settings", return_value=settings):
        response = _post_firmado(client, secret_firma="otro-secreto")

    assert response.status_code == 401
    webhook.ejecutar.assert_not_called()


def test_billing_deshabilitado_sigue_respondiendo_503_con_secreto_vacio():
    settings = Settings(
        _env_file=None, APP_ENV="development", DEBUG=True, BILLING_HABILITADO=False, MP_WEBHOOK_SECRET=""
    )
    client, webhook = _cliente()

    with patch("src.infrastructure.fastapi.routes.billing_router.get_settings", return_value=settings):
        response = _post_firmado(client, secret_firma="")

    assert response.status_code == 503
    assert "deshabilitado" in response.json()["detail"]
    webhook.ejecutar.assert_not_called()
