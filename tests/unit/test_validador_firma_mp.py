"""tests/unit/test_validador_firma_mp.py."""

import hashlib
import hmac

import pytest

from src.domain.billing.servicios.validador_firma_mp import (
    FirmaWebhookInvalidaError,
    validar_firma_mp,
)

SECRET = "shhh-secreto-de-prueba"


def _firmar(data_id: str, x_request_id: str, ts: str, secret: str = SECRET) -> str:
    manifest = f"id:{data_id.lower()};request-id:{x_request_id};ts:{ts};"
    v1 = hmac.new(secret.encode("utf-8"), manifest.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"ts={ts},v1={v1}"


def test_firma_valida_no_lanza():
    x_sig = _firmar("PREAPPROVAL-123", "req-abc", "1700000000")
    validar_firma_mp(x_sig, "req-abc", "PREAPPROVAL-123", SECRET)


def test_firma_es_case_insensitive_en_data_id():
    x_sig = _firmar("preapproval-123", "req-abc", "1700000000")
    validar_firma_mp(x_sig, "req-abc", "PREAPPROVAL-123", SECRET)


def test_firma_invalida_con_secreto_incorrecto():
    x_sig = _firmar("PREAPPROVAL-123", "req-abc", "1700000000", secret="otro-secreto")
    with pytest.raises(FirmaWebhookInvalidaError):
        validar_firma_mp(x_sig, "req-abc", "PREAPPROVAL-123", SECRET)


def test_firma_invalida_si_cambia_el_data_id():
    x_sig = _firmar("PREAPPROVAL-123", "req-abc", "1700000000")
    with pytest.raises(FirmaWebhookInvalidaError):
        validar_firma_mp(x_sig, "req-abc", "PREAPPROVAL-999", SECRET)


def test_header_malformado_lanza():
    with pytest.raises(FirmaWebhookInvalidaError):
        validar_firma_mp("esto-no-es-valido", "req-abc", "PREAPPROVAL-123", SECRET)
