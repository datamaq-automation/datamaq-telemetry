"""tests/unit/test_mercadopago_gateway.py — sin red real, vía httpx.MockTransport."""

from decimal import Decimal

import httpx
import pytest

from src.infrastructure.mercadopago.gateway import MercadoPagoGateway


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.mercadopago.com")


def test_crear_preapproval_envia_el_payload_correcto_y_parsea_init_point():
    capturado = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["method"] = request.method
        capturado["url"] = str(request.url)
        capturado["auth"] = request.headers.get("authorization")
        capturado["body"] = request.content
        return httpx.Response(
            201,
            json={
                "id": "preap-123",
                "init_point": "https://www.mercadopago.com.ar/subscriptions/checkout?preapproval_id=preap-123",
            },
        )

    gateway = MercadoPagoGateway("TEST-TOKEN", client=_client(handler))
    resultado = gateway.crear_preapproval(
        external_reference="org-1:plan-pro",
        monto_mensual_ars=Decimal("5000"),
        motivo="Suscripción DataMaq — Plan PRO",
        payer_email="cliente@example.com",
        back_url="https://app.datamaq.com.ar/facturacion?estado=ok",
    )

    assert resultado.id == "preap-123"
    assert "preapproval_id=preap-123" in resultado.init_point
    assert capturado["method"] == "POST"
    assert capturado["url"].endswith("/preapproval")
    assert capturado["auth"] == "Bearer TEST-TOKEN"

    import json

    payload = json.loads(capturado["body"])
    assert payload["external_reference"] == "org-1:plan-pro"
    assert payload["payer_email"] == "cliente@example.com"
    assert payload["auto_recurring"]["transaction_amount"] == 5000.0
    assert payload["auto_recurring"]["currency_id"] == "ARS"


def test_crear_preapproval_usa_sandbox_init_point_si_no_hay_init_point():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"id": "preap-1", "sandbox_init_point": "https://sandbox.example/preap-1"})

    gateway = MercadoPagoGateway("TEST-TOKEN", client=_client(handler))
    resultado = gateway.crear_preapproval("org-1:plan-pro", Decimal("5000"), "motivo", "a@b.com", "https://back")

    assert resultado.init_point == "https://sandbox.example/preap-1"


def test_crear_preapproval_error_http_propaga_excepcion():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"message": "bad request"})

    gateway = MercadoPagoGateway("TEST-TOKEN", client=_client(handler))
    with pytest.raises(httpx.HTTPStatusError):
        gateway.crear_preapproval("org-1:plan-pro", Decimal("5000"), "motivo", "a@b.com", "https://back")


def test_obtener_preapproval_parsea_next_payment_date_top_level():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "preap-1",
                "status": "authorized",
                "external_reference": "org-1:plan-pro",
                "next_payment_date": "2026-10-15T00:00:00.000Z",
            },
        )

    gateway = MercadoPagoGateway("TEST-TOKEN", client=_client(handler))
    info = gateway.obtener_preapproval("preap-1")

    assert info.status == "authorized"
    assert info.external_reference == "org-1:plan-pro"
    assert info.next_payment_date is not None
    assert info.next_payment_date.year == 2026
    assert info.next_payment_date.month == 10


def test_obtener_preapproval_parsea_next_payment_date_anidado_en_auto_recurring():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "preap-1",
                "status": "authorized",
                "external_reference": "org-1:plan-pro",
                "auto_recurring": {"next_payment_date": "2026-11-01T00:00:00.000Z"},
            },
        )

    gateway = MercadoPagoGateway("TEST-TOKEN", client=_client(handler))
    info = gateway.obtener_preapproval("preap-1")

    assert info.next_payment_date is not None
    assert info.next_payment_date.month == 11


def test_obtener_preapproval_sin_next_payment_date_devuelve_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"id": "preap-1", "status": "cancelled", "external_reference": "org-1:plan-pro"}
        )

    gateway = MercadoPagoGateway("TEST-TOKEN", client=_client(handler))
    info = gateway.obtener_preapproval("preap-1")

    assert info.next_payment_date is None
    assert info.status == "cancelled"
