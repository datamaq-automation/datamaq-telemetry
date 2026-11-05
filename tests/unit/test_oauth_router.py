"""tests/unit/test_oauth_router.py — Tests unitarios para endpoints OAuth (C4-17, C4-20, C4-22, Issue #136)."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.domain.oauth.exceptions import OAuthError
from src.infrastructure.fastapi.dependencies import (
    get_jwt_token_service,
    get_oauth_repository,
    get_usuarios_repository,
)
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.settings.config import Settings, get_settings


def _cliente_oauth(settings_override: Settings | None = None):
    app = create_app()
    mock_repo_oauth = MagicMock()
    mock_jwt = MagicMock()
    mock_repo_usuarios = MagicMock()

    app.dependency_overrides[get_oauth_repository] = lambda: mock_repo_oauth
    app.dependency_overrides[get_jwt_token_service] = lambda: mock_jwt
    app.dependency_overrides[get_usuarios_repository] = lambda: mock_repo_usuarios

    if settings_override is not None:
        app.dependency_overrides[get_settings] = lambda: settings_override

    return TestClient(app), mock_repo_oauth


def test_discovery_oauth_authorization_server_derivacion_dinamica_request():
    """C4-17: El issuer y endpoints se derivan de request.base_url si API_BASE_URL no está seteado."""
    client, _ = _cliente_oauth()

    response = client.get("/.well-known/oauth-authorization-server")

    assert response.status_code == 200
    data = response.json()
    assert data["issuer"] == "http://testserver"
    assert data["token_endpoint"] == "http://testserver/oauth/token"
    assert data["revocation_endpoint"] == "http://testserver/oauth/revoke"
    assert data["registration_endpoint"] == "http://testserver/oauth/register"
    assert data["authorization_endpoint"] == "http://localhost:5173/oauth/authorize"


def test_discovery_oauth_authorization_server_settings_personalizados():
    """C4-17: El issuer y app_base respetan API_BASE_URL y APP_BASE_URL configurados."""
    custom_settings = Settings(
        API_BASE_URL="https://mi-api.empresa.com/",
        APP_BASE_URL="https://mi-app.empresa.com/",
    )
    client, _ = _cliente_oauth(settings_override=custom_settings)

    response = client.get("/.well-known/oauth-authorization-server")

    assert response.status_code == 200
    data = response.json()
    assert data["issuer"] == "https://mi-api.empresa.com"
    assert data["authorization_endpoint"] == "https://mi-app.empresa.com/oauth/authorize"
    assert data["token_endpoint"] == "https://mi-api.empresa.com/oauth/token"
    assert data["revocation_endpoint"] == "https://mi-api.empresa.com/oauth/revoke"
    assert data["registration_endpoint"] == "https://mi-api.empresa.com/oauth/register"


def test_metadata_oauth_protected_resource_derivacion_dinamica():
    """C4-17: Metadatos de RFC 9728 derivan dinámicamente el issuer."""
    custom_settings = Settings(API_BASE_URL="https://api-custom.datamaq.local")
    client, _ = _cliente_oauth(settings_override=custom_settings)

    response = client.get("/.well-known/oauth-protected-resource")

    assert response.status_code == 200
    data = response.json()
    assert data["resource"] == "https://api-custom.datamaq.local/mcp"
    assert data["authorization_servers"] == ["https://api-custom.datamaq.local"]


def test_canjear_token_oauth_error_inesperado_sanitiza_excepcion():
    """C4-22 / Issue #136: Excepciones imprevistas no filtran trazas ni str(exc) a clientes anónimos."""
    client, _ = _cliente_oauth()

    # Simulamos un fallo interno inesperado en el caso de uso
    with patch(
        "src.infrastructure.fastapi.routes.oauth_router.CanjearTokenOAuthUseCase.ejecutar",
        side_effect=RuntimeError("Fallo interno sensible con clave secreta: SECRET_KEY_12345"),
    ):
        response = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": "codigo-invalido",
                "client_id": "cliente-test",
                "code_verifier": "v" * 64,
            },
        )

    assert response.status_code == 400
    data = response.json()
    assert data["error"] == "invalid_request"
    assert data["error_description"] == "Solicitud de token inválida o corrupta."
    # Verificación estricta de no fuga de información sensible
    assert "SECRET_KEY_12345" not in response.text
    assert "RuntimeError" not in response.text


def test_canjear_token_oauth_error_oauth_controlado_preserva_descripcion():
    """Errores controlados de tipo OAuthError preservan su código y descripción de protocolo RFC 6749."""
    client, _ = _cliente_oauth()

    with patch(
        "src.infrastructure.fastapi.routes.oauth_router.CanjearTokenOAuthUseCase.ejecutar",
        side_effect=OAuthError("invalid_grant", "Código de autorización expirado o no encontrado.", 400),
    ):
        response = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": "codigo-expirado",
                "client_id": "cliente-test",
                "code_verifier": "v" * 64,
            },
        )

    assert response.status_code == 400
    data = response.json()
    assert data["error"] == "invalid_grant"
    assert data["error_description"] == "Código de autorización expirado o no encontrado."


def test_revocar_token_oauth_ante_excepcion_retorna_200_rfc7009():
    """C4-20: Revocación ante fallo imprevisto emite warning pero retorna HTTP 200 según RFC 7009."""
    client, mock_repo = _cliente_oauth()
    mock_repo.obtener_por_token.side_effect = RuntimeError("Error imprevisto en BD de tokens")

    response = client.post(
        "/oauth/revoke",
        data={"token": "token-a-revocar", "client_id": "cliente-test"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "revoked"}
