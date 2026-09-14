"""src/domain/billing/servicios/validador_firma_mp.py.

Valida la firma HMAC-SHA256 que Mercado Pago manda en el header `x-signature` de cada
notificación de webhook, según el algoritmo documentado por MP:
https://www.mercadopago.com.ar/developers/es/docs/checkout-api/webhooks/additional-info

Header: "x-signature: ts=<epoch>,v1=<hex-hmac>"
Manifest firmado: "id:{data_id};request-id:{x_request_id};ts:{ts};"
(data_id en minúsculas si viene del query param `data.id` de la URL de notificación).
"""

import hashlib
import hmac


class FirmaWebhookInvalidaError(Exception):
    """Lanzada cuando el header x-signature no valida contra el secreto configurado."""


def _parsear_x_signature(x_signature: str) -> tuple[str, str]:
    partes = dict(par.strip().split("=", 1) for par in x_signature.split(",") if "=" in par)
    ts = partes.get("ts")
    v1 = partes.get("v1")
    if not ts or not v1:
        raise FirmaWebhookInvalidaError("Header x-signature con formato inesperado (faltan ts o v1).")
    return ts, v1


def validar_firma_mp(
    x_signature: str,
    x_request_id: str,
    data_id: str,
    secret: str,
) -> None:
    """No retorna nada si la firma es válida; lanza FirmaWebhookInvalidaError si no."""
    ts, v1_recibido = _parsear_x_signature(x_signature)
    manifest = f"id:{data_id.lower()};request-id:{x_request_id};ts:{ts};"
    v1_calculado = hmac.new(secret.encode("utf-8"), manifest.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(v1_calculado, v1_recibido):
        raise FirmaWebhookInvalidaError("Firma x-signature no coincide con el secreto configurado.")
