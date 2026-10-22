"""src/domain/oauth/entities.py — Entidades de dominio puras para OAuth 2.0 y PKCE."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class OAuthClient:
    """Cliente OAuth 2.0 registrado (ej. Claude.ai)."""

    client_id: str
    client_name: str
    redirect_uris: tuple[str, ...]
    created_at: datetime


@dataclass(frozen=True)
class OAuthCode:
    """Código de autorización temporal emitido con PKCE (TTL 5 minutos)."""

    code_hash: str
    client_id: str
    user_id: str
    organization_id: str | None
    redirect_uri: str
    code_challenge: str
    code_challenge_method: str
    scope: str
    expires_at: datetime
    used: bool
    created_at: datetime


@dataclass(frozen=True)
class OAuthRefreshToken:
    """Token de refresco criptográfico persistido con rotación (TTL 30 días)."""

    token_hash: str
    client_id: str
    user_id: str
    organization_id: str | None
    scope: str
    expires_at: datetime
    revoked_at: datetime | None
    created_at: datetime


@dataclass(frozen=True)
class OAuthTokenPair:
    """Respuesta estándar OAuth 2.0 con access token y refresh token."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 86400
    scope: str = ""
