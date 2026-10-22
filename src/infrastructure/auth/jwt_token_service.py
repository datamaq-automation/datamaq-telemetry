"""src/infrastructure/auth/jwt_token_service.py."""

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any

from src.domain.auth.ports import GeneradorTokenPort


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


class JwtTokenService(GeneradorTokenPort):
    ALGORITMO = "HS256"

    def __init__(self, secreto: str):
        self.secreto = secreto

    def _firmar(self, mensaje: bytes) -> bytes:
        return hmac.new(self.secreto.encode("utf-8"), mensaje, hashlib.sha256).digest()

    def generar(
        self,
        usuario_id: str,
        usuario: str,
        expira_en: datetime,
        rol: str = "operador",
        organizacion_id: str | None = None,
        scope: str | None = None,
        client_id: str | None = None,
    ) -> str:
        encabezado = _b64url(json.dumps({"alg": self.ALGORITMO, "typ": "JWT"}, separators=(",", ":")).encode("utf-8"))
        ahora = datetime.now(timezone.utc)
        payload: dict[str, object] = {
            "sub": usuario_id,
            "usuario": usuario,
            "exp": int(expira_en.timestamp()),
            "rol": rol,
            "iat": int(ahora.timestamp()),
        }
        if organizacion_id is not None:
            payload["org"] = organizacion_id
        if scope is not None:
            payload["scope"] = scope
        if client_id is not None:
            payload["client_id"] = client_id
        cuerpo = _b64url(
            json.dumps(
                payload,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        mensaje = f"{encabezado}.{cuerpo}".encode("ascii")
        firma = _b64url(self._firmar(mensaje))
        return f"{encabezado}.{cuerpo}.{firma}"

    def _verificar_con_secreto(self, token: str, secreto: str) -> dict[str, Any] | None:
        try:
            encabezado, cuerpo, firma = token.split(".")
        except (ValueError, AttributeError):
            return None

        try:
            cabecera = json.loads(_b64url_decode(encabezado).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

        if cabecera.get("alg") != self.ALGORITMO:
            return None

        mensaje = f"{encabezado}.{cuerpo}".encode("ascii")
        firma_esperada = _b64url(hmac.new(secreto.encode("utf-8"), mensaje, hashlib.sha256).digest())
        if not hmac.compare_digest(firma, firma_esperada):
            return None

        try:
            payload = json.loads(_b64url_decode(cuerpo).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

        exp = payload.get("exp")
        if not isinstance(exp, (int, float)) or exp <= datetime.now(timezone.utc).timestamp():
            return None

        return payload

    def generar_mfa(self, usuario_id: str, usuario: str, expira_en: datetime) -> str:
        encabezado = _b64url(json.dumps({"alg": self.ALGORITMO, "typ": "JWT"}, separators=(",", ":")).encode("utf-8"))
        ahora = datetime.now(timezone.utc)
        cuerpo = _b64url(
            json.dumps(
                {
                    "sub": usuario_id,
                    "usuario": usuario,
                    "mfa_pending": True,
                    "exp": int(expira_en.timestamp()),
                    "iat": int(ahora.timestamp()),
                },
                separators=(",", ":"),
            ).encode("utf-8")
        )
        mensaje = f"{encabezado}.{cuerpo}".encode("ascii")
        firma = _b64url(self._firmar(mensaje))
        return f"{encabezado}.{cuerpo}.{firma}"

    def verificar(self, token: str, secretos_adicionales: list[str] | None = None) -> dict[str, Any] | None:
        payload = self._verificar_con_secreto(token, self.secreto)
        if payload is not None:
            if payload.get("mfa_pending") or payload.get("purpose") == "pwd_reset":
                return None
            return payload
        for secreto in secretos_adicionales or []:
            payload = self._verificar_con_secreto(token, secreto)
            if payload is not None:
                if payload.get("mfa_pending") or payload.get("purpose") == "pwd_reset":
                    return None
                return payload
        return None

    def verificar_mfa(self, token: str) -> dict[str, Any] | None:
        payload = self._verificar_con_secreto(token, self.secreto)
        if payload is not None and payload.get("mfa_pending") is True:
            return payload
        return None

    def generar_recuperacion(self, usuario_id: str, usuario: str, expira_en: datetime, hash_actual: str) -> str:
        encabezado = _b64url(json.dumps({"alg": self.ALGORITMO, "typ": "JWT"}, separators=(",", ":")).encode("utf-8"))
        ahora = datetime.now(timezone.utc)
        pwh = hashlib.sha256(hash_actual.encode("utf-8")).hexdigest()[:16]
        cuerpo = _b64url(
            json.dumps(
                {
                    "sub": usuario_id,
                    "usuario": usuario,
                    "purpose": "pwd_reset",
                    "pwh": pwh,
                    "exp": int(expira_en.timestamp()),
                    "iat": int(ahora.timestamp()),
                },
                separators=(",", ":"),
            ).encode("utf-8")
        )
        mensaje = f"{encabezado}.{cuerpo}".encode("ascii")
        firma = _b64url(self._firmar(mensaje))
        return f"{encabezado}.{cuerpo}.{firma}"

    def verificar_recuperacion(self, token: str) -> dict[str, Any] | None:
        payload = self._verificar_con_secreto(token, self.secreto)
        if payload is not None and payload.get("purpose") == "pwd_reset":
            return payload
        return None
