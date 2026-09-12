"""tests/unit/test_security_jwt.py — JWT robusto: validación de `alg` y rotación de secretos vía clave dual."""

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

from src.infrastructure.auth.jwt_token_service import JwtTokenService
from src.infrastructure.fastapi import dependencies as deps


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _firmar(secreto: str, mensaje: bytes) -> str:
    firma = hmac.new(secreto.encode("utf-8"), mensaje, hashlib.sha256).digest()
    return _b64url(firma)


def _token_con_alg(alg: str, secreto: str) -> str:
    encabezado = _b64url(json.dumps({"alg": alg, "typ": "JWT"}, separators=(",", ":")).encode("utf-8"))
    exp = int((datetime.now(timezone.utc) + timedelta(minutes=30)).timestamp())
    cuerpo = _b64url(
        json.dumps(
            {"sub": "usuario-1", "usuario": "operador@planta.local", "rol": "operador", "exp": exp},
            separators=(",", ":"),
        ).encode("utf-8")
    )
    mensaje = f"{encabezado}.{cuerpo}".encode("ascii")
    return f"{encabezado}.{cuerpo}.{_firmar(secreto, mensaje)}"


def test_verificar_rechaza_alg_none():
    token = _token_con_alg("none", "s3cr3t0")
    assert JwtTokenService("s3cr3t0").verificar(token) is None


def test_verificar_rechaza_alg_rs256():
    token = _token_con_alg("RS256", "s3cr3t0")
    assert JwtTokenService("s3cr3t0").verificar(token) is None


def test_verificar_acepta_token_alg_hs256():
    service = JwtTokenService("s3cr3t0")
    token = service.generar(
        "usuario-1",
        "operador@planta.local",
        datetime.now(timezone.utc) + timedelta(minutes=30),
        rol="operador",
    )

    claims = service.verificar(token)

    assert claims is not None
    assert claims["sub"] == "usuario-1"
    assert claims["usuario"] == "operador@planta.local"
    assert claims["rol"] == "operador"


def test_verificar_con_clave_anterior():
    expira_en = datetime.now(timezone.utc) + timedelta(minutes=30)
    token = JwtTokenService("clave-antigua").generar("usuario-1", "operador@planta.local", expira_en)

    assert JwtTokenService("clave-nueva").verificar(token, secretos_adicionales=["clave-antigua"]) is not None
    assert JwtTokenService("clave-nueva").verificar(token) is None


def test_token_valido_acepta_clave_anterior():
    expira_en = datetime.now(timezone.utc) + timedelta(minutes=30)
    token = JwtTokenService("clave-antigua").generar("usuario-1", "operador@planta.local", expira_en)

    assert deps.token_valido(token, None, "clave-nueva", "clave-antigua") is True
