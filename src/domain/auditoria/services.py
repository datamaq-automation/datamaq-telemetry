"""src/domain/auditoria/services.py — Servicios del dominio de auditoría."""

from typing import Any


class SanitizadorAuditoriaService:
    """Garantiza diffs seguros en metadatos para cumplimiento estricto de ISO 27001 y Ley 25.326.

    PROHIBIDO registrar passwords, secretos, tokens o material criptográfico sensible.
    """

    PATRONES_SENSIBLES: frozenset[str] = frozenset(
        {
            "password",
            "contrasena",
            "contraseña",
            "password_hash",
            "hash_contrasena",
            "secret",
            "secreto",
            "totp_secret",
            "backup_codes",
            "totp_backup_codes",
            "token",
            "jwt",
            "api_key",
            "secret_key",
            "bearer",
            "access_token",
            "refresh_token",
        }
    )

    @classmethod
    def sanitizar_metadatos(cls, metadatos: dict[str, Any] | None) -> dict[str, Any] | None:
        if metadatos is None:
            return None

        resultado: dict[str, Any] = {}
        for clave, valor in metadatos.items():
            clave_normalizada = str(clave).lower().strip()
            es_sensible = any(patron in clave_normalizada for patron in cls.PATRONES_SENSIBLES)

            if es_sensible:
                resultado[clave] = "[REDACTED]"
            elif isinstance(valor, dict):
                resultado[clave] = cls.sanitizar_metadatos(valor)
            elif isinstance(valor, list):
                resultado[clave] = [cls.sanitizar_metadatos(item) if isinstance(item, dict) else item for item in valor]
            else:
                resultado[clave] = valor

        return resultado
