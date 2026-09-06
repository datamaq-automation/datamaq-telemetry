from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from src.domain.auth.entities import UsuarioAuth


class RepositorioUsuariosPort(ABC):
    @abstractmethod
    def obtener_por_usuario(self, usuario: str) -> UsuarioAuth | None:
        pass

    @abstractmethod
    def guardar(self, usuario: UsuarioAuth) -> UsuarioAuth:
        pass


class GeneradorTokenPort(ABC):
    @abstractmethod
    def generar(self, usuario_id: str, usuario: str, expira_en: datetime, rol: str = "operador") -> str:
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
