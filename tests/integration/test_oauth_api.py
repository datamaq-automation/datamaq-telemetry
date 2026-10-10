"""tests/integration/test_oauth_api.py — Pruebas de integración de la API para OAuth 2.0 PKCE."""

import uuid
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from src.domain.oauth.services import calcular_code_challenge
from src.infrastructure.fastapi.dependencies import get_db_session, get_usuario_actual
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.sqlalchemy.models import Base, UserModel
from src.infrastructure.sqlalchemy.repositories.oauth_repository import sembrar_clientes_oauth


def _crear_app_test() -> tuple[Any, str]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as db:
        sembrar_clientes_oauth(db)
        user_id = str(uuid.uuid4())
        nuevo = UserModel(
            id=user_id,
            username=f"oauth_test_{user_id[:8]}@datamaq.com",
            password_hash="hash",
            role="ingeniero",
            organization_id=None,
            is_active=True,
        )
        db.add(nuevo)
        db.commit()

    app = create_app()

    def _override_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db_session] = _override_db
    return app, user_id


def test_oauth_metadata_discovery_rfc8414():
    """Valida que GET /.well-known/oauth-authorization-server exponga la metadata RFC 8414."""
    app = create_app()
    with TestClient(app) as client:
        res = client.get("/.well-known/oauth-authorization-server")
        assert res.status_code == 200
        data = res.json()
        assert "issuer" in data
        assert data["authorization_endpoint"].endswith("/oauth/authorize")
        assert data["token_endpoint"].endswith("/oauth/token")
        assert data["revocation_endpoint"].endswith("/oauth/revoke")
        assert "code" in data["response_types_supported"]
        assert "authorization_code" in data["grant_types_supported"]
        assert "refresh_token" in data["grant_types_supported"]
        assert "S256" in data["code_challenge_methods_supported"]
        assert "read:telemetria" in data["scopes_supported"]


def test_oauth_metadata_protected_resource_rfc9728():
    """Valida que GET /.well-known/oauth-protected-resource exponga metadata RFC 9728 para clientes MCP."""
    app = create_app()
    with TestClient(app) as client:
        res = client.get("/.well-known/oauth-protected-resource")
        assert res.status_code == 200
        data = res.json()
        assert data["resource"].endswith("/mcp")
        assert "authorization_servers" in data


def test_oauth_flujo_completo_pkce_y_rotacion_refresh():
    """Valida el ciclo de vida completo de OAuth 2.0 PKCE: consentimiento -> code -> tokens -> refresh -> revoke."""
    app, user_id = _crear_app_test()

    # Simular sesión activa del usuario para la pantalla de consentimiento
    app.dependency_overrides[get_usuario_actual] = lambda: {
        "sub": user_id,
        "org": "org_durax_1",
        "rol": "ingeniero",
    }

    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    challenge = calcular_code_challenge(verifier)

    with TestClient(app) as client:
        # 1. Autorizar y obtener code
        auth_payload = {
            "client_id": "claude-ai",
            "redirect_uri": "https://claude.ai/api/mcp/oauth_callback",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "state_seguro_123",
            "scope": "read:telemetria read:analitica",
        }
        auth_res = client.post("/api/v1/oauth/authorize", json=auth_payload)
        assert auth_res.status_code == 200
        auth_data = auth_res.json()
        code = auth_data["code"]
        assert code is not None
        assert auth_data["state"] == "state_seguro_123"
        assert "code=" in auth_data["redirect_uri"]

        # 2. Canjear code con form-data x-www-form-urlencoded (estándar RFC 6749)
        token_payload = {
            "grant_type": "authorization_code",
            "client_id": "claude-ai",
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": "https://claude.ai/api/mcp/oauth_callback",
        }
        token_res = client.post("/oauth/token", data=token_payload)
        assert token_res.status_code == 200
        tokens = token_res.json()
        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]
        assert tokens["token_type"] == "bearer"
        assert tokens["expires_in"] == 86400
        assert access_token is not None
        assert refresh_token is not None

        # 3. Intentar reutilizar el mismo code (debe fallar con invalid_grant)
        reuse_res = client.post("/oauth/token", data=token_payload)
        assert reuse_res.status_code == 400
        assert reuse_res.json()["error"] == "invalid_grant"

        # 4. Listar integraciones del usuario
        integraciones_res = client.get("/api/v1/usuarios/integraciones")
        assert integraciones_res.status_code == 200
        integraciones = integraciones_res.json()
        assert len(integraciones) >= 1
        assert any(i["client_id"] == "claude-ai" for i in integraciones)

        # 5. Rotar refresh token (grant_type=refresh_token)
        refresh_payload = {
            "grant_type": "refresh_token",
            "client_id": "claude-ai",
            "refresh_token": refresh_token,
        }
        refresh_res = client.post("/oauth/token", data=refresh_payload)
        assert refresh_res.status_code == 200
        nuevos_tokens = refresh_res.json()
        nuevo_refresh = nuevos_tokens["refresh_token"]
        assert nuevo_refresh != refresh_token

        # 6. Intentar usar el refresh anterior (debe fallar por rotación)
        stale_res = client.post("/oauth/token", data=refresh_payload)
        assert stale_res.status_code == 400
        assert stale_res.json()["error"] == "invalid_grant"

        # 7. Revocar el nuevo refresh token (RFC 7009)
        revoke_res = client.post("/oauth/revoke", data={"token": nuevo_refresh})
        assert revoke_res.status_code == 200
        assert revoke_res.json() == {"status": "revoked"}

        # 8. Comprobar que ya no es válido para refrescar
        after_revoke_res = client.post(
            "/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": "claude-ai",
                "refresh_token": nuevo_refresh,
            },
        )
        assert after_revoke_res.status_code == 400


def test_oauth_token_verifier_invalido():
    """Valida que un code_verifier incorrecto devuelva error 400 invalid_grant."""
    app, user_id = _crear_app_test()
    app.dependency_overrides[get_usuario_actual] = lambda: {
        "sub": user_id,
        "org": "org_durax_1",
        "rol": "ingeniero",
    }

    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    challenge = calcular_code_challenge(verifier)

    with TestClient(app) as client:
        auth_res = client.post(
            "/api/v1/oauth/authorize",
            json={
                "client_id": "claude-ai",
                "redirect_uri": "https://claude.ai/api/mcp/oauth_callback",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
        )
        code = auth_res.json()["code"]

        token_res = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": "claude-ai",
                "code": code,
                "code_verifier": "verifier_invalido_pero_valido_en_longitud_43_caracteres_min",
                "redirect_uri": "https://claude.ai/api/mcp/oauth_callback",
            },
        )
        assert token_res.status_code == 400
        assert token_res.json()["error"] == "invalid_grant"


def test_oauth_revocar_integracion_por_cliente():
    """Valida que DELETE /api/v1/usuarios/integraciones/{client_id} revoque el acceso."""
    app, user_id = _crear_app_test()
    app.dependency_overrides[get_usuario_actual] = lambda: {
        "sub": user_id,
        "org": "org_durax_1",
        "rol": "ingeniero",
    }

    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    challenge = calcular_code_challenge(verifier)

    with TestClient(app) as client:
        auth_res = client.post(
            "/api/v1/oauth/authorize",
            json={
                "client_id": "claude-ai",
                "redirect_uri": "https://claude.ai/api/mcp/oauth_callback",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
        )
        code = auth_res.json()["code"]

        client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": "claude-ai",
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": "https://claude.ai/api/mcp/oauth_callback",
            },
        )

        del_res = client.delete("/api/v1/usuarios/integraciones/claude-ai")
        assert del_res.status_code == 200
        assert del_res.json()["status"] == "ok"
        assert del_res.json()["revocados"] >= 1

        # Ver que ya no figure en la lista
        list_res = client.get("/api/v1/usuarios/integraciones")
        assert list_res.status_code == 200
        assert len([i for i in list_res.json() if i["client_id"] == "claude-ai"]) == 0


def test_oauth_consent_info_y_consent_flow():
    """Valida los endpoints de la UI de consentimiento (consent-info y consent)."""
    app, user_id = _crear_app_test()
    app.dependency_overrides[get_usuario_actual] = lambda: {
        "sub": user_id,
        "org": "org-durax",
        "rol": "ingeniero",
    }

    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    challenge = calcular_code_challenge(verifier)

    with TestClient(app) as client:
        # 1. GET /api/v1/oauth/consent-info
        info_res = client.get("/api/v1/oauth/consent-info?client_id=claude-ai&scope=read:telemetria")
        assert info_res.status_code == 200
        info_data = info_res.json()
        assert info_data["client_id"] == "claude-ai"
        assert info_data["client_icon"] == "anthropic"
        assert info_data["organizacion_id"] == "org-durax"
        assert "planta" in info_data["planta_activa_id"]
        assert len(info_data["scopes"]) == 1
        assert info_data["scopes"][0]["scope"] == "read:telemetria"
        assert "Lectura" in info_data["scopes"][0]["descripcion"]

        # 2. POST /api/v1/oauth/consent (cancelado por el usuario)
        denied_res = client.post(
            "/api/v1/oauth/consent",
            json={
                "client_id": "claude-ai",
                "redirect_uri": "https://claude.ai/api/mcp/oauth/callback",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "scope": "read:telemetria",
                "state": "state_123",
                "aprobado": False,
            },
        )
        assert denied_res.status_code == 200
        assert "error=access_denied" in denied_res.json()["redirect_url"]
        assert "state=state_123" in denied_res.json()["redirect_url"]

        # 3. POST /api/v1/oauth/consent (aprobado por el usuario)
        approved_res = client.post(
            "/api/v1/oauth/consent",
            json={
                "client_id": "claude-ai",
                "redirect_uri": "https://claude.ai/api/mcp/oauth/callback",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "scope": "read:telemetria",
                "state": "state_123",
                "aprobado": True,
            },
        )
        assert approved_res.status_code == 200
        redirect_url = approved_res.json()["redirect_url"]
        assert "code=" in redirect_url
        assert "state=state_123" in redirect_url
