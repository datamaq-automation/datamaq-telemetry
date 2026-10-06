"""Servicios de dominio para cambio de contraseña autenticado."""

import random
import string
from datetime import datetime, timedelta, timezone


class GeneradorCodigoOTP:
    """Genera códigos OTP de 4 dígitos."""

    @staticmethod
    def generar() -> str:
        """Genera código numérico de 4 dígitos (0000-9999)."""
        return "".join(random.choices(string.digits, k=4))


class ValidadorContraseña:
    """Valida requisitos de contraseña."""

    MINIMO_CARACTERES = 8
    REQUIERE_MAYUSCULA = True
    REQUIERE_DIGITO = True

    @classmethod
    def validar(cls, password: str) -> tuple[bool, list[str]]:
        """Valida contraseña. Retorna (es_válida, lista_errores)."""
        errores: list[str] = []

        if len(password) < cls.MINIMO_CARACTERES:
            errores.append(f"Mínimo {cls.MINIMO_CARACTERES} caracteres")

        if cls.REQUIERE_MAYUSCULA and not any(c.isupper() for c in password):
            errores.append("Requiere mayúscula")

        if cls.REQUIERE_DIGITO and not any(c.isdigit() for c in password):
            errores.append("Requiere dígito")

        return len(errores) == 0, errores


class ServicioTTLValidacion:
    """Calcula y valida TTL de códigos OTP."""

    TTL_MINUTOS = 10

    @classmethod
    def calcular_expiracion(cls) -> datetime:
        """Calcula timestamp de expiración (ahora + TTL_MINUTOS)."""
        return datetime.now(timezone.utc) + timedelta(minutes=cls.TTL_MINUTOS)

    @classmethod
    def esta_expirado(cls, ttl_expira: datetime) -> bool:
        """Verifica si una validación está expirada."""
        return datetime.now(timezone.utc) > ttl_expira
