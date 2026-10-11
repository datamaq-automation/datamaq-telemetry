import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from src.application.dtos.oauth_dtos import (
    OAuthAuthorizeRequestDTO,
    OAuthAuthorizeResponseDTO,
    OAuthClientRegistrationRequestDTO,
    OAuthClientRegistrationResponseDTO,
    OAuthConsentInfoResponseDTO,
    OAuthConsentProcessRequestDTO,
    OAuthConsentProcessResponseDTO,
    OAuthDiscoveryMetadataDTO,
    OAuthRevokeRequestDTO,
    OAuthScopeDetalleDTO,
    OAuthTokenRequestDTO,
    OAuthTokenResponseDTO,
)
from src.application.use_cases.oauth.autorizar_consentimiento import AutorizarConsentimientoUseCase
from src.application.use_cases.oauth.canjear_token_oauth import CanjearTokenOAuthUseCase
from src.application.use_cases.oauth.gestionar_integraciones_usuario import (
    GestionarIntegracionesUsuarioUseCase,
)
from src.application.use_cases.oauth.revocar_token_oauth import RevocarTokenOAuthUseCase
from src.domain.auth.ports import RepositorioUsuariosPort
from src.domain.oauth.exceptions import OAuthError
from src.domain.oauth.ports import OAuthRepositoryPort
from src.infrastructure.auth.jwt_token_service import JwtTokenService
from src.infrastructure.fastapi.dependencies import (
    get_jwt_token_service,
    get_oauth_repository,
    get_usuario_actual,
    get_usuarios_repository,
)
from src.infrastructure.settings.config import Settings, get_settings

router = APIRouter(tags=["OAuth 2.0 PKCE"])


@router.get("/.well-known/oauth-authorization-server", response_model=OAuthDiscoveryMetadataDTO)
def metadata_oauth_authorization_server(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> OAuthDiscoveryMetadataDTO:
    """Descubrimiento de metadatos del Servidor de Autorización OAuth 2.0 según RFC 8414."""
    es_prod = settings.APP_ENV == "production"
    issuer = "https://api.datamaq.com.ar" if es_prod else str(request.base_url).rstrip("/")
    app_base = "https://app.datamaq.com.ar" if es_prod else "http://localhost:5173"

    return OAuthDiscoveryMetadataDTO(
        issuer=issuer,
        authorization_endpoint=f"{app_base}/oauth/authorize",
        token_endpoint=f"{issuer}/oauth/token",
        revocation_endpoint=f"{issuer}/oauth/revoke",
        registration_endpoint=f"{issuer}/oauth/register",
        response_types_supported=["code"],
        grant_types_supported=["authorization_code", "refresh_token"],
        code_challenge_methods_supported=["S256"],
        scopes_supported=["read:telemetria", "read:analitica", "read:alertas"],
        token_endpoint_auth_methods_supported=["none"],
    )


@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/mcp")
@router.get("/.well-known/oauth-protected-resource/{resource_path:path}")
def metadata_oauth_protected_resource(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    resource_path: str = "",
) -> dict[str, Any]:
    """Descubrimiento de metadatos de Recurso Protegido OAuth 2.0 según RFC 9728 para clientes MCP."""
    es_prod = settings.APP_ENV == "production"
    issuer = "https://api.datamaq.com.ar" if es_prod else str(request.base_url).rstrip("/")
    return {
        "resource": f"{issuer}/mcp",
        "authorization_servers": [issuer],
        "scopes_supported": ["read:telemetria", "read:analitica", "read:alertas"],
        "bearer_methods_supported": ["header"],
    }


@router.post(
    "/oauth/register",
    response_model=OAuthClientRegistrationResponseDTO,
    status_code=201,
)
@router.post(
    "/api/v1/oauth/register",
    response_model=OAuthClientRegistrationResponseDTO,
    status_code=201,
)
def registrar_cliente_dinamico_oauth(
    dto: OAuthClientRegistrationRequestDTO,
    repo_oauth: Annotated[OAuthRepositoryPort, Depends(get_oauth_repository)],
) -> Any:
    """Registro dinámico de clientes OAuth 2.0 según RFC 7591."""
    es_claude = any(
        "claude.ai" in uri.lower() or "claude.com" in uri.lower() or "anthropic" in uri.lower()
        for uri in dto.redirect_uris
    )
    client_id = "claude-ai" if es_claude else f"dyn-{uuid.uuid4().hex[:12]}"
    client_name = dto.client_name or ("Claude (Anthropic)" if es_claude else "Cliente Dinámico")

    cliente = repo_oauth.registrar_o_actualizar_cliente(
        client_id=client_id,
        client_name=client_name,
        redirect_uris=dto.redirect_uris,
    )

    return OAuthClientRegistrationResponseDTO(
        client_id=cliente.client_id,
        client_name=cliente.client_name,
        redirect_uris=list(cliente.redirect_uris),
        grant_types=dto.grant_types or ["authorization_code", "refresh_token"],
        response_types=dto.response_types or ["code"],
        token_endpoint_auth_method="none",
    )


DESCRIPCIONES_SCOPES = {
    "read:telemetria": "Lectura de curvas de potencia, factor de potencia y analítica de planta",
    "read:analitica": "Diagnóstico de banco de capacitores y cos φ",
    "read:alertas": "Monitoreo y consulta de alertas operativas",
}


@router.get("/api/v1/oauth/consent-info", response_model=OAuthConsentInfoResponseDTO)
def obtener_consent_info_oauth(
    client_id: str,
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    repo_oauth: Annotated[OAuthRepositoryPort, Depends(get_oauth_repository)],
    scope: str = "read:telemetria",
) -> Any:
    """Retorna información institucional del cliente y permisos para la pantalla de consentimiento."""
    cliente = repo_oauth.obtener_cliente(client_id)
    if cliente is None:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_client", "error_description": f"Cliente '{client_id}' no registrado"},
        )

    icon = "anthropic" if ("claude" in client_id.lower() or "anthropic" in cliente.client_name.lower()) else "datamaq"
    scopes_solicitados = [s.strip() for s in scope.replace(",", " ").split() if s.strip()]
    if not scopes_solicitados:
        scopes_solicitados = ["read:telemetria"]

    lista_scopes = [
        OAuthScopeDetalleDTO(
            scope=s,
            descripcion=DESCRIPCIONES_SCOPES.get(s, "Acceso de lectura autorizado"),
        )
        for s in scopes_solicitados
    ]

    org_id = claims.get("org")
    planta_id = f"planta-{org_id}" if org_id else "planta-principal"
    planta_nombre = f"Planta {org_id.replace('org-', '').title()}" if org_id else "Planta Principal"

    return OAuthConsentInfoResponseDTO(
        client_id=cliente.client_id,
        client_name=cliente.client_name,
        client_icon=icon,
        organizacion_id=org_id,
        planta_activa_id=planta_id,
        planta_activa_nombre=planta_nombre,
        scopes=lista_scopes,
    )


@router.post("/api/v1/oauth/consent", response_model=OAuthConsentProcessResponseDTO)
def procesar_consentimiento_oauth(
    dto: OAuthConsentProcessRequestDTO,
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    repo_oauth: Annotated[OAuthRepositoryPort, Depends(get_oauth_repository)],
) -> Any:
    """Procesa la aprobación o cancelación del usuario en la pantalla de consentimiento."""
    if not dto.aprobado:
        sep = "&" if "?" in dto.redirect_uri else "?"
        params = "error=access_denied&error_description=El+usuario+cancelo+la+autorizacion"
        if dto.state:
            params += f"&state={dto.state}"
        return OAuthConsentProcessResponseDTO(redirect_url=f"{dto.redirect_uri}{sep}{params}")

    try:
        uc = AutorizarConsentimientoUseCase(repo_oauth)
        res = uc.ejecutar(
            dto=OAuthAuthorizeRequestDTO(
                client_id=dto.client_id,
                redirect_uri=dto.redirect_uri,
                code_challenge=dto.code_challenge,
                code_challenge_method=dto.code_challenge_method,
                scope=dto.scope,
                state=dto.state,
            ),
            usuario_id=str(claims["sub"]),
            organizacion_id=claims.get("org"),
        )
        return OAuthConsentProcessResponseDTO(redirect_url=res.redirect_uri)
    except OAuthError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.error, "error_description": exc.description},
        )


@router.post("/api/v1/oauth/authorize", response_model=OAuthAuthorizeResponseDTO)
def autorizar_consentimiento_oauth(
    dto: OAuthAuthorizeRequestDTO,
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    repo_oauth: Annotated[OAuthRepositoryPort, Depends(get_oauth_repository)],
) -> Any:
    """Registra el consentimiento del usuario autenticado y genera el código de autorización PKCE."""
    try:
        uc = AutorizarConsentimientoUseCase(repo_oauth)
        return uc.ejecutar(
            dto=dto,
            usuario_id=str(claims["sub"]),
            organizacion_id=claims.get("org"),
        )
    except OAuthError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.error, "error_description": exc.description},
        )


@router.post("/oauth/token", response_model=OAuthTokenResponseDTO)
@router.post("/api/v1/oauth/token", response_model=OAuthTokenResponseDTO)
async def canjear_token_oauth(
    request: Request,
    repo_oauth: Annotated[OAuthRepositoryPort, Depends(get_oauth_repository)],
    token_service: Annotated[JwtTokenService, Depends(get_jwt_token_service)],
    repo_usuarios: Annotated[RepositorioUsuariosPort, Depends(get_usuarios_repository)],
) -> Any:
    """Canjea un código de autorización PKCE o renueva un token mediante refresh token (RFC 6749 + RFC 7636)."""
    try:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            data = await request.json()
        else:
            form = await request.form()
            data = dict(form)

        dto = OAuthTokenRequestDTO.model_validate(data)
        uc = CanjearTokenOAuthUseCase(repo_oauth, token_service, repo_usuarios)
        return uc.ejecutar(dto)
    except OAuthError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.error, "error_description": exc.description},
        )
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_request", "error_description": str(exc)},
        )


@router.post("/oauth/revoke")
@router.post("/api/v1/oauth/revoke")
async def revocar_token_oauth(
    request: Request,
    repo_oauth: Annotated[OAuthRepositoryPort, Depends(get_oauth_repository)],
) -> Any:
    """Revoca un token OAuth 2.0 según RFC 7009."""
    try:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            data = await request.json()
        else:
            form = await request.form()
            data = dict(form)

        token = str(data.get("token", "")).strip()
        if token:
            client_id = data.get("client_id")
            RevocarTokenOAuthUseCase(repo_oauth).ejecutar(
                OAuthRevokeRequestDTO(token=token, client_id=str(client_id) if client_id else None)
            )
        return JSONResponse(status_code=200, content={"status": "revoked"})
    except Exception:
        # RFC 7009: siempre responde 200 aunque el token no exista
        return JSONResponse(status_code=200, content={"status": "revoked"})


@router.get("/api/v1/usuarios/integraciones")
def listar_integraciones_usuario(
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    repo_oauth: Annotated[OAuthRepositoryPort, Depends(get_oauth_repository)],
) -> Any:
    """Lista las aplicaciones e integraciones conectadas del usuario para la pantalla de perfil."""
    uc = GestionarIntegracionesUsuarioUseCase(repo_oauth)
    return uc.listar(str(claims["sub"]))


@router.delete("/api/v1/usuarios/integraciones/{client_id}")
def revocar_integracion_usuario(
    client_id: str,
    claims: Annotated[dict[str, Any], Depends(get_usuario_actual)],
    repo_oauth: Annotated[OAuthRepositoryPort, Depends(get_oauth_repository)],
) -> Any:
    """Revoca el acceso de una integración específica para el usuario actual (ISO 27001)."""
    uc = GestionarIntegracionesUsuarioUseCase(repo_oauth)
    revocados = uc.revocar_por_cliente(str(claims["sub"]), client_id)
    return {"client_id": client_id, "revocados": revocados, "status": "ok"}
