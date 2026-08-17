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

    def generar(self, usuario_id: str, usuario: str, expira_en: datetime, rol: str = "operador") -> str:
        encabezado = _b64url(json.dumps({"alg": self.ALGORITMO, "typ": "JWT"}, separators=(",", ":")).encode("utf-8"))
        ahora = datetime.now(timezone.utc)
        cuerpo = _b64url(
            json.dumps(
                {
                    "sub": usuario_id,
                    "usuario": usuario,
                    "exp": int(expira_en.timestamp()),
                    "rol": rol,
                    "iat": int(ahora.timestamp()),
                },
                separators=(",", ":"),
            ).encode("utf-8")
        )
        mensaje = f"{encabezado}.{cuerpo}".encode("ascii")
        firma = _b64url(self._firmar(mensaje))
        return f"{encabezado}.{cuerpo}.{firma}"

    def verificar(self, token: str) -> dict[str, Any] | None:
        try:
            encabezado, cuerpo, firma = token.split(".")
        except (ValueError, AttributeError):
            return None

        mensaje = f"{encabezado}.{cuerpo}".encode("ascii")
        if not hmac.compare_digest(firma, _b64url(self._firmar(mensaje))):
            return None

        try:
            payload = json.loads(_b64url_decode(cuerpo).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

        exp = payload.get("exp")
        if not isinstance(exp, (int, float)) or exp <= datetime.now(timezone.utc).timestamp():
            return None

        return payload
