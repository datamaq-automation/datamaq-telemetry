import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta


class HashContrasenaService:
    """Hashea y verifica contraseñas con scrypt (stdlib, sin dependencias)."""

    N: int = 2**14
    R: int = 8
    P: int = 1
    SALT_BYTES: int = 16
    DIGEST_BYTES: int = 32

    @classmethod
    def generar_hash(cls, contrasena: str) -> str:
        salt = secrets.token_bytes(cls.SALT_BYTES)
        digest = hashlib.scrypt(
            contrasena.encode("utf-8"),
            salt=salt,
            n=cls.N,
            r=cls.R,
            p=cls.P,
            dklen=cls.DIGEST_BYTES,
        )
        return "$".join(
            (
                "scrypt",
                str(cls.N),
                str(cls.R),
                str(cls.P),
                base64.b64encode(salt).decode("ascii"),
                base64.b64encode(digest).decode("ascii"),
            )
        )

    @classmethod
    def verificar(cls, contrasena: str, hash_almacenado: str) -> bool:
        try:
            algoritmo, n_raw, r_raw, p_raw, salt_b64, digest_b64 = hash_almacenado.split("$")
            if algoritmo != "scrypt":
                return False
            n = int(n_raw)
            r = int(r_raw)
            p = int(p_raw)
            salt = base64.b64decode(salt_b64)
            esperado = base64.b64decode(digest_b64)
        except (ValueError, TypeError):
            return False

        digest = hashlib.scrypt(
            contrasena.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(esperado),
        )
        return hmac.compare_digest(digest, esperado)


class PoliticaExpiracionService:
    @staticmethod
    def calcular_expiracion(ahora: datetime, minutos_validez: int) -> datetime:
        return ahora + timedelta(minutes=minutos_validez)
