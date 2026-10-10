"""src/application/dtos/oauth_dtos.py — DTOs para el Servidor de Autorización OAuth 2.0 y PKCE."""

from typing import Literal

from pydantic import BaseModel, Field


class OAuthAuthorizeRequestDTO(BaseModel):
    """Solicitud de autorización enviada por la pantalla de consentimiento de app-datamaq."""

    client_id: str = Field(min_length=1, max_length=128)
    redirect_uri: str = Field(min_length=1, max_length=512)
    code_challenge: str = Field(min_length=43, max_length=128)
    code_challenge_method: Literal["S256"] = "S256"
    state: str | None = Field(default=None, max_length=512)
    scope: str = Field(default="read:telemetria read:analitica read:alertas", max_length=256)


class OAuthAuthorizeResponseDTO(BaseModel):
    """Respuesta con el código emitido y la URL final de redirección hacia Claude."""

    code: str
    state: str | None = None
    redirect_uri: str


class OAuthScopeDetalleDTO(BaseModel):
    """Detalle de un scope solicitado para la pantalla de consentimiento."""

    scope: str
    descripcion: str


class OAuthConsentInfoResponseDTO(BaseModel):
    """Información devuelta a la pantalla de consentimiento institucional (app-datamaq)."""

    client_id: str
    client_name: str
    client_icon: str = "datamaq"
    organizacion_id: str | None = None
    planta_activa_id: str | None = None
    planta_activa_nombre: str | None = None
    scopes: list[OAuthScopeDetalleDTO] = Field(default_factory=list)


class OAuthConsentProcessRequestDTO(BaseModel):
    """Payload de decisión del usuario en la pantalla de consentimiento (app-datamaq)."""

    client_id: str = Field(min_length=1, max_length=128)
    redirect_uri: str = Field(min_length=1, max_length=512)
    code_challenge: str = Field(min_length=43, max_length=128)
    code_challenge_method: Literal["S256"] = "S256"
    scope: str = Field(default="read:telemetria", max_length=256)
    state: str | None = Field(default=None, max_length=512)
    aprobado: bool = True


class OAuthConsentProcessResponseDTO(BaseModel):
    """Respuesta con la URL final de redirección con code o error."""

    redirect_url: str


class OAuthTokenRequestDTO(BaseModel):
    """Parámetros recibidos en POST /oauth/token (form o json)."""

    grant_type: Literal["authorization_code", "refresh_token"]
    client_id: str | None = Field(default=None, max_length=128)
    redirect_uri: str | None = Field(default=None, max_length=512)
    code: str | None = Field(default=None, max_length=256)
    code_verifier: str | None = Field(default=None, max_length=256)
    refresh_token: str | None = Field(default=None, max_length=256)


class OAuthTokenResponseDTO(BaseModel):
    """Respuesta estándar RFC 6749 para emisión de tokens."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = 86400
    refresh_token: str
    scope: str = ""


class OAuthRevokeRequestDTO(BaseModel):
    """Solicitud de revocación RFC 7009."""

    token: str = Field(min_length=1, max_length=512)
    client_id: str | None = Field(default=None, max_length=128)


class OAuthDiscoveryMetadataDTO(BaseModel):
    """Metadatos del servidor de autorización según RFC 8414."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    revocation_endpoint: str
    response_types_supported: list[str] = Field(default_factory=lambda: ["code"])
    grant_types_supported: list[str] = Field(default_factory=lambda: ["authorization_code", "refresh_token"])
    code_challenge_methods_supported: list[str] = Field(default_factory=lambda: ["S256"])
    scopes_supported: list[str] = Field(default_factory=lambda: ["read:telemetria", "read:analitica", "read:alertas"])
    token_endpoint_auth_methods_supported: list[str] = Field(default_factory=lambda: ["none"])
