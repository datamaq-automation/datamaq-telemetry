"""src/infrastructure/auth/cifrador_2fa.py."""
import base64
import hashlib

from cryptography.fernet import Fernet

from src.domain.auth.ports import CifradorSecreto2FAPort


class CifradorSecreto2FA(CifradorSecreto2FAPort):
    def __init__(self, clave_maestra: str):
        clave_sha256 = hashlib.sha256(clave_maestra.encode("utf-8")).digest()
        clave_fernet = base64.urlsafe_b64encode(clave_sha256)
        self._fernet = Fernet(clave_fernet)

    def cifrar(self, texto_plano: str) -> str:
        return self._fernet.encrypt(texto_plano.encode("utf-8")).decode("utf-8")

    def descifrar(self, texto_cifrado: str) -> str:
        return self._fernet.decrypt(texto_cifrado.encode("utf-8")).decode("utf-8")
