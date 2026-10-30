"""src/domain/auth/ports.py."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from src.domain.auth.entities import (
    AccesoPlantaUsuario,
    DispositivoConfiable,
    UsuarioAuth,
    ValidacionCambioContrasena,
)


class RepositorioUsuariosPort(ABC):
    @abstractmethod
    def obtener_por_usuario(self, usuario: str) -> UsuarioAuth | None:
        pass

    def obtener_por_id(self, usuario_id: str) -> UsuarioAuth | None:
        return None

    def listar_todos(self) -> list[UsuarioAuth]:
        """Todas las cuentas, de todas las organizaciones. Por defecto vacío (fail-closed)."""
        return []

    @abstractmethod
    def guardar(self, usuario: UsuarioAuth) -> UsuarioAuth:
        pass


class RepositorioAccesosPlantaPort(ABC):
    """Asignación explícita usuario ↔ planta (`user_facility_access`).

    Sin filas para un usuario, la política de dominio cae al comportamiento
    histórico: todas las plantas de su organización, con permiso de cambio.
    """

    @abstractmethod
    def listar_por_usuario(self, usuario_id: str) -> list[AccesoPlantaUsuario]:
        pass

    @abstractmethod
    def reemplazar(self, usuario_id: str, accesos: list[AccesoPlantaUsuario]) -> list[AccesoPlantaUsuario]:
        """Sustituye el conjunto completo de accesos del usuario (idempotente)."""
        pass


class GeneradorTokenPort(ABC):
    @abstractmethod
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
        pass

    @abstractmethod
    def verificar(self, token: str) -> dict[str, Any] | None:
        pass

    @abstractmethod
    def generar_mfa(self, usuario_id: str, usuario: str, expira_en: datetime) -> str:
        pass

    @abstractmethod
    def verificar_mfa(self, token: str) -> dict[str, Any] | None:
        pass

    def generar_recuperacion(self, usuario_id: str, usuario: str, expira_en: datetime, hash_actual: str) -> str:
        return ""

    def verificar_recuperacion(self, token: str) -> dict[str, Any] | None:
        return None


class ServicioTOTPPort(ABC):
    @abstractmethod
    def generar_secreto(self) -> str:
        pass

    @abstractmethod
    def verificar_codigo(self, secreto: str, codigo: str) -> bool:
        pass

    @abstractmethod
    def generar_uri(self, usuario: str, secreto: str, emisor: str = "DataMaq") -> str:
        pass

    @abstractmethod
    def generar_qr_svg(self, uri: str) -> str:
        pass


class CifradorSecreto2FAPort(ABC):
    @abstractmethod
    def cifrar(self, texto_plano: str) -> str:
        pass

    @abstractmethod
    def descifrar(self, texto_cifrado: str) -> str:
        pass


class ServicioEmailPort(ABC):
    @abstractmethod
    def enviar_email_recuperacion(self, destinatario: str, enlace_restablecimiento: str) -> bool:
        pass

    @abstractmethod
    def enviar_codigo_cambio_contrasena(self, destinatario: str, codigo: str) -> bool:
        """Envía el OTP de 4 dígitos. El código nunca debe quedar en logs."""

    @abstractmethod
    def notificar_cambio_contrasena(self, destinatario: str, momento: datetime, ip: str | None) -> bool:
        """Confirma que la contraseña cambió. No incluye la contraseña ni el código."""


class RepositorioDispositivosConfiablesPort(ABC):
    @abstractmethod
    def obtener_por_hash(self, token_hash: str) -> DispositivoConfiable | None:
        pass

    @abstractmethod
    def guardar(self, dispositivo: DispositivoConfiable) -> DispositivoConfiable:
        pass

    @abstractmethod
    def actualizar_acceso(self, id: str, ip: str, ultimo_acceso: datetime) -> None:
        pass

    @abstractmethod
    def revocar_todos_de_usuario(self, usuario_id: str) -> int:
        pass


class RepositorioCambioContrasenaPort(ABC):
    """Validaciones OTP de cambio de contraseña y su auditoría propia."""

    @abstractmethod
    def crear_validacion(
        self, usuario_id: str, codigo_hash: str, ttl_expira: datetime, ahora: datetime
    ) -> ValidacionCambioContrasena:
        pass

    @abstractmethod
    def invalidar_vigentes(self, usuario_id: str, ahora: datetime) -> None:
        pass

    @abstractmethod
    def contar_solicitudes_desde(self, usuario_id: str, desde: datetime) -> int:
        pass

    @abstractmethod
    def contar_auditoria_desde(self, usuario_id: str, estado: str, desde: datetime) -> int:
        """Cuenta eventos de auditoría de cambio de contraseña del usuario con ese estado desde `desde`."""

    @abstractmethod
    def obtener_vigente(self, usuario_id: str, ahora: datetime) -> ValidacionCambioContrasena | None:
        pass

    @abstractmethod
    def registrar_intento_fallido(self, validacion_id: int) -> int:
        """Incrementa intentos_fallidos y devuelve el total nuevo."""

    @abstractmethod
    def consumir(self, validacion_id: int, ahora: datetime) -> None:
        pass

    @abstractmethod
    def registrar_auditoria(
        self, usuario_id: str, estado: str, ip: str | None, user_agent: str | None, ahora: datetime
    ) -> None:
        pass
