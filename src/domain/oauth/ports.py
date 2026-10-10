"""src/domain/oauth/ports.py — Puertos de dominio para persistencia y servicios OAuth 2.0."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from src.domain.oauth.entities import OAuthClient, OAuthCode, OAuthRefreshToken


class OAuthRepositoryPort(ABC):
    """Puerto de persistencia para clientes, códigos y tokens OAuth 2.0."""

    @abstractmethod
    def obtener_cliente(self, client_id: str) -> OAuthClient | None:
        """Obtiene un cliente registrado por su identificador."""
        pass

    @abstractmethod
    def guardar_codigo(self, codigo: OAuthCode) -> None:
        """Persiste un código de autorización temporal."""
        pass

    @abstractmethod
    def obtener_codigo(self, code_hash: str) -> OAuthCode | None:
        """Recupera un código de autorización por su hash."""
        pass

    @abstractmethod
    def consumir_codigo(self, code_hash: str) -> bool:
        """Marca un código como consumido atómicamente. Retorna True si se consumió, False si ya estaba usado."""
        pass

    @abstractmethod
    def guardar_refresh_token(self, refresh_token: OAuthRefreshToken) -> None:
        """Persiste un refresh token."""
        pass

    @abstractmethod
    def obtener_refresh_token(self, token_hash: str) -> OAuthRefreshToken | None:
        """Recupera un refresh token por su hash."""
        pass

    @abstractmethod
    def revocar_refresh_token(self, token_hash: str, ahora: datetime) -> bool:
        """Revoca un refresh token específico."""
        pass

    @abstractmethod
    def revocar_tokens_usuario_cliente(self, user_id: str, client_id: str, ahora: datetime) -> int:
        """Revoca todos los refresh tokens de un usuario para un cliente particular."""
        pass

    @abstractmethod
    def listar_integraciones_usuario(self, user_id: str) -> list[dict[str, Any]]:
        """Lista las integraciones autorizadas activas para la vista de perfil del usuario."""
        pass

    @abstractmethod
    def registrar_o_actualizar_cliente(self, client_id: str, client_name: str, redirect_uris: list[str]) -> OAuthClient:
        """Registra un nuevo cliente o sincroniza sus redirect_uris (RFC 7591 Dynamic Client Registration)."""
        pass
