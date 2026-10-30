"""src/domain/usuarios/servicios_contrasena.py.

Servicios de dominio para cambio de contraseña autenticado."""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone


class GeneradorCodigoOTP:
    """Genera, firma y verifica códigos OTP de 4 dígitos.

    El espacio es 10^4: la protección real es el límite de intentos del caso de uso, no la
    longitud del código. El código se guarda como HMAC-SHA256 con clave del servidor, nunca en claro.
    """

    @staticmethod
    def generar() -> str:
        """Genera código numérico de 4 dígitos (0000-9999) con CSPRNG."""
        return f"{secrets.randbelow(10_000):04d}"

    @staticmethod
    def calcular_hmac(codigo: str, clave: str) -> str:
        """HMAC-SHA256 hex del código con la clave del servidor."""
        return hmac.new(clave.encode("utf-8"), codigo.encode("utf-8"), hashlib.sha256).hexdigest()

    @classmethod
    def verificar(cls, codigo: str, hash_guardado: str, clave: str) -> bool:
        """Compara en tiempo constante el código recibido contra el HMAC guardado."""
        return hmac.compare_digest(cls.calcular_hmac(codigo, clave), hash_guardado)


class ValidadorContraseña:
    """Valida requisitos de contraseña del cambio autenticado (spec: mayúscula, minúscula, dígito)."""

    MINIMO_CARACTERES = 8
    REQUIERE_MAYUSCULA = True
    REQUIERE_MINUSCULA = True
    REQUIERE_DIGITO = True

    @classmethod
    def validar(cls, password: str) -> tuple[bool, list[str]]:
        """Valida contraseña. Retorna (es_válida, lista_errores)."""
        errores: list[str] = []

        if len(password) < cls.MINIMO_CARACTERES:
            errores.append(f"Mínimo {cls.MINIMO_CARACTERES} caracteres")

        if cls.REQUIERE_MAYUSCULA and not any(c.isupper() for c in password):
            errores.append("Requiere mayúscula")

        if cls.REQUIERE_MINUSCULA and not any(c.islower() for c in password):
            errores.append("Requiere minúscula")

        if cls.REQUIERE_DIGITO and not any(c.isdigit() for c in password):
            errores.append("Requiere dígito")

        return len(errores) == 0, errores


class ServicioTTLValidacion:
    """TTL del código y límites del flujo de cambio de contraseña."""

    TTL_MINUTOS = 10
    MAX_INTENTOS_CODIGO = 5
    MAX_SOLICITUDES = 5
    VENTANA_SOLICITUDES_MINUTOS = 10

    @classmethod
    def calcular_expiracion(cls) -> datetime:
        """Calcula timestamp de expiración (ahora + TTL_MINUTOS)."""
        return datetime.now(timezone.utc) + timedelta(minutes=cls.TTL_MINUTOS)

    @classmethod
    def esta_expirado(cls, ttl_expira: datetime) -> bool:
        """Verifica si una validación está expirada."""
        return datetime.now(timezone.utc) > ttl_expira

    @classmethod
    def inicio_ventana_solicitudes(cls, ahora: datetime) -> datetime:
        """Inicio de la ventana en la que se cuentan las solicitudes de código."""
        return ahora - timedelta(minutes=cls.VENTANA_SOLICITUDES_MINUTOS)
