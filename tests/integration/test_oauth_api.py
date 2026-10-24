"""tests/integration/test_oauth_api.py — Pruebas de integración de la API para OAuth 2.0 PKCE."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.domain.oauth.services import calcular_code_challenge
from src.infrastructure.auth.jwt_token_service import JwtTokenService
from src.infrastructure.fastapi.dependencies import get_db_session, get_oauth_repository, get_usuario_actual
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.settings.config import get_settings
from src.infrastructure.sqlalchemy.models import Base, UserModel
from src.infrastructure.sqlalchemy.oauth_models import OAuthRefreshTokenModel
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
        assert data["registration_endpoint"].endswith("/oauth/register")
        assert "code" in data["response_types_supported"]
        assert "authorization_code" in data["grant_types_supported"]
        assert "refresh_token" in data["grant_types_supported"]
        assert "S256" in data["code_challenge_methods_supported"]
        assert "read:telemetria" in data["scopes_supported"]


def test_oauth_dynamic_client_registration_rfc7591():
    """Valida el registro dinámico de clientes OAuth 2.0 (RFC 7591) usado por Claude.ai."""
    app, _ = _crear_app_test()
    with TestClient(app) as client:
        # Petición de auto-registro típica de Claude.ai
        reg_payload = {
            "client_name": "Claude",
            "redirect_uris": ["https://claude.ai/api/mcp/oauth/callback"],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
        }
        res = client.post("/oauth/register", json=reg_payload)
        assert res.status_code == 201
        data = res.json()
        assert data["client_id"] == "claude-ai"
        assert "https://claude.ai/api/mcp/oauth/callback" in data["redirect_uris"]
        assert data["token_endpoint_auth_method"] == "none"

        # También debe responder en el alias /api/v1/oauth/register
        reg_payload_alias = {
            "client_name": "Otro Cliente",
            "redirect_uris": ["http://localhost:3000/oauth/cb"],
        }
        res_alias = client.post("/api/v1/oauth/register", json=reg_payload_alias)
        assert res_alias.status_code == 201
        data_alias = res_alias.json()
        assert data_alias["client_id"].startswith("dyn-")
        assert "http://localhost:3000/oauth/cb" in data_alias["redirect_uris"]


def test_oauth_metadata_protected_resource_rfc9728():
    """Valida que GET /.well-known/oauth-protected-resource (y /mcp) expongan metadata RFC 9728 para clientes MCP."""
    app = create_app()
    with TestClient(app) as client:
        # Consulta sin sufijo
        res = client.get("/.well-known/oauth-protected-resource")
        assert res.status_code == 200
        data = res.json()
        assert data["resource"].endswith("/mcp")
        assert "authorization_servers" in data

        # Consulta con sufijo de recurso /mcp (solicitado por clientes MCP como Claude)
        res_mcp = client.get("/.well-known/oauth-protected-resource/mcp")
        assert res_mcp.status_code == 200
        data_mcp = res_mcp.json()
        assert data_mcp["resource"].endswith("/mcp")
        assert "authorization_servers" in data_mcp
        assert "scopes_supported" in data_mcp


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


REDIRECT_URIS = {
    "claude-ai": "https://claude.ai/api/mcp/oauth_callback",
    "datamaq-mcp-client": "http://localhost:8000/callback",
}
VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"


def _token_login(user_id: str) -> str:
    """JWT de login normal (sin client_id), firmado con la clave de la app bajo test."""
    return JwtTokenService(get_settings().API_SECRET_KEY).generar(
        usuario_id=user_id,
        usuario="oauth_test@datamaq.com",
        expira_en=datetime.now(timezone.utc) + timedelta(hours=1),
        rol="ingeniero",
        organizacion_id="org_durax_1",
    )


def _headers_login(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token_login(user_id)}"}


def _headers_bearer(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _emitir_tokens_oauth(
    client: TestClient, login_headers: dict[str, str], client_id: str = "claude-ai"
) -> dict[str, Any]:
    """Recorre authorize + token con PKCE y devuelve la respuesta de /oauth/token (access y refresh)."""
    redirect_uri = REDIRECT_URIS[client_id]
    auth_res = client.post(
        "/api/v1/oauth/authorize",
        headers=login_headers,
        json={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": calcular_code_challenge(VERIFIER),
            "code_challenge_method": "S256",
        },
    )
    assert auth_res.status_code == 200
    token_res = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": auth_res.json()["code"],
            "code_verifier": VERIFIER,
            "redirect_uri": redirect_uri,
        },
    )
    assert token_res.status_code == 200
    return token_res.json()


class _RelojAtrasado(datetime):
    """`datetime` cuyo `now()` marca una hora antes: los tokens emitidos con él nacen "hace una hora"."""

    @classmethod
    def now(cls, tz: Any = None) -> datetime:
        return datetime.now(tz) - timedelta(hours=1)


def _atrasar_reloj(m: pytest.MonkeyPatch) -> None:
    """Hace que el canje y la firma del JWT usen la hora atrasada (el iat y el created_at del refresh)."""
    m.setattr("src.application.use_cases.oauth.canjear_token_oauth.datetime", _RelojAtrasado)
    m.setattr("src.infrastructure.auth.jwt_token_service.datetime", _RelojAtrasado)


def _estado(client: TestClient, access_token: str) -> int:
    return client.get("/api/v1/usuarios/integraciones", headers=_headers_bearer(access_token)).status_code


def _crear_usuario(app: Any) -> str:
    """Agrega otro usuario a la base de test (la misma que usa la app vía dependency_overrides)."""
    generador = app.dependency_overrides[get_db_session]()
    db = next(generador)
    user_id = str(uuid.uuid4())
    db.add(
        UserModel(
            id=user_id,
            username=f"otro_{user_id[:8]}@datamaq.com",
            password_hash="hash",
            role="ingeniero",
            organization_id=None,
            is_active=True,
        )
    )
    db.commit()
    generador.close()
    return user_id


def test_oauth_access_token_deja_de_valer_al_desconectar_integracion():
    """Issue #33: tras DELETE /integraciones/{client_id} el access token emitido a ese cliente da 401."""
    app, user_id = _crear_app_test()
    login_headers = _headers_login(user_id)

    with TestClient(app) as client:
        access_token = _emitir_tokens_oauth(client, login_headers)["access_token"]

        # Mientras la integración está conectada, el access token se acepta.
        assert _estado(client, access_token) == 200

        # El usuario desconecta la integración desde su sesión normal.
        del_res = client.delete("/api/v1/usuarios/integraciones/claude-ai", headers=login_headers)
        assert del_res.status_code == 200
        assert del_res.json()["revocados"] >= 1

        # El access token (24 h) ya no debe aceptarse, aunque no haya vencido.
        rechazado = client.get("/api/v1/usuarios/integraciones", headers=_headers_bearer(access_token))
        assert rechazado.status_code == 401
        assert rechazado.json()["detail"] == "credenciales_invalidas"

        # La sesión de login normal (sin client_id) no se ve afectada.
        assert client.get("/api/v1/usuarios/integraciones", headers=login_headers).status_code == 200


def test_oauth_access_token_viejo_no_revive_al_reconectar_el_mismo_cliente(monkeypatch):
    """El access token emitido antes de desconectar no vuelve a valer cuando se reconecta el mismo client_id."""
    app, user_id = _crear_app_test()
    login_headers = _headers_login(user_id)

    with TestClient(app) as client:
        with monkeypatch.context() as m:
            _atrasar_reloj(m)
            viejo = _emitir_tokens_oauth(client, login_headers)["access_token"]
        assert _estado(client, viejo) == 200

        client.delete("/api/v1/usuarios/integraciones/claude-ai", headers=login_headers)
        assert _estado(client, viejo) == 401

        # Reconexión del mismo cliente: el refresh nuevo es posterior al access viejo.
        nuevo = _emitir_tokens_oauth(client, login_headers)["access_token"]
        assert _estado(client, nuevo) == 200
        assert _estado(client, viejo) == 401


def test_oauth_autorizar_de_nuevo_sin_desconectar_no_corta_el_access_vigente(monkeypatch):
    """Autorizar otra vez el mismo cliente sin desconectar deja activo el refresh original: el access sigue valiendo."""
    app, user_id = _crear_app_test()
    login_headers = _headers_login(user_id)

    with TestClient(app) as client:
        with monkeypatch.context() as m:
            _atrasar_reloj(m)
            viejo = _emitir_tokens_oauth(client, login_headers)["access_token"]

        _emitir_tokens_oauth(client, login_headers)
        assert _estado(client, viejo) == 200


def test_oauth_rotar_refresh_emite_access_nuevo_y_reemplaza_al_anterior(monkeypatch):
    """Rotación real (POST /oauth/token grant_type=refresh_token): el access nuevo vale y el emitido antes deja de valer.

    Decisión (Issue #33): el access solo vale mientras exista un refresh sin revocar creado hasta su emisión.
    Rotar revoca el viejo y crea uno posterior, así que el access anterior queda reemplazado por el nuevo.
    """
    app, user_id = _crear_app_test()
    login_headers = _headers_login(user_id)

    with TestClient(app) as client:
        with monkeypatch.context() as m:
            _atrasar_reloj(m)
            emitidos = _emitir_tokens_oauth(client, login_headers)
        assert _estado(client, emitidos["access_token"]) == 200

        rotado = client.post(
            "/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": "claude-ai",
                "refresh_token": emitidos["refresh_token"],
            },
        )
        assert rotado.status_code == 200
        assert rotado.json()["refresh_token"] != emitidos["refresh_token"]

        assert _estado(client, rotado.json()["access_token"]) == 200
        assert _estado(client, emitidos["access_token"]) == 401


def test_oauth_refresh_vencido_sin_revocar_no_corta_access_token_vigente():
    """Decisión: el chequeo mira solo revoked_at. El refresh (30 d) vive más que el access (1 d) emitido con él."""
    app, user_id = _crear_app_test()
    login_headers = _headers_login(user_id)

    with TestClient(app) as client:
        access_token = _emitir_tokens_oauth(client, login_headers)["access_token"]

        # Forzamos el caso límite: refresh vencido pero no revocado.
        generador = app.dependency_overrides[get_db_session]()
        db = next(generador)
        db.query(OAuthRefreshTokenModel).filter(OAuthRefreshTokenModel.user_id == user_id).update(
            {"expires_at": datetime.now(timezone.utc) - timedelta(hours=1)}
        )
        db.commit()
        generador.close()

        assert _estado(client, access_token) == 200


def test_oauth_falla_cerrada_si_el_repositorio_oauth_lanza():
    """Si el chequeo de la integración falla, el access token OAuth no pasa (ni como 200 ni sin respuesta de error)."""
    app, user_id = _crear_app_test()
    login_headers = _headers_login(user_id)

    class _RepoQueFalla:
        def tiene_integracion_activa(self, *args: Any, **kwargs: Any) -> bool:
            raise RuntimeError("base caída")

    with TestClient(app) as client:
        access_token = _emitir_tokens_oauth(client, login_headers)["access_token"]
        app.dependency_overrides[get_oauth_repository] = lambda: _RepoQueFalla()
        res = client.get("/api/v1/usuarios/integraciones", headers=_headers_bearer(access_token))
        assert res.status_code == 401
        assert res.json()["detail"] == "credenciales_invalidas"


def test_ws_live_rechaza_el_access_token_de_una_integracion_desconectada():
    """/ws/live valida el JWT por su cuenta: también debe cerrar con 4401 si la integración fue desconectada."""
    app, user_id = _crear_app_test()
    login_headers = _headers_login(user_id)

    with TestClient(app) as client:
        access_token = _emitir_tokens_oauth(client, login_headers)["access_token"]

        # Con la integración conectada, el stream acepta el access token y sigue abierto.
        with client.websocket_connect("/ws/live", headers=_headers_bearer(access_token)) as ws:
            ws.send_text("ping")

        client.delete("/api/v1/usuarios/integraciones/claude-ai", headers=login_headers)

        with client.websocket_connect("/ws/live", headers=_headers_bearer(access_token)) as ws:
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_text()
        assert exc.value.code == 4401
        assert exc.value.reason == "token_invalido"

        # El token de login normal (sin client_id) sigue conectando.
        with client.websocket_connect("/ws/live", headers=login_headers) as ws:
            ws.send_text("ping")


def test_oauth_desconectar_un_cliente_no_corta_a_otro_del_mismo_usuario():
    app, user_id = _crear_app_test()
    login_headers = _headers_login(user_id)

    with TestClient(app) as client:
        claude = _emitir_tokens_oauth(client, login_headers, "claude-ai")["access_token"]
        conector = _emitir_tokens_oauth(client, login_headers, "datamaq-mcp-client")["access_token"]

        client.delete("/api/v1/usuarios/integraciones/claude-ai", headers=login_headers)

        assert _estado(client, claude) == 401
        assert _estado(client, conector) == 200


def test_oauth_desconectar_no_corta_a_otro_usuario_con_el_mismo_client_id():
    app, user_id = _crear_app_test()
    otro_usuario = _crear_usuario(app)

    with TestClient(app) as client:
        propio = _emitir_tokens_oauth(client, _headers_login(user_id))["access_token"]
        ajeno = _emitir_tokens_oauth(client, _headers_login(otro_usuario))["access_token"]

        client.delete("/api/v1/usuarios/integraciones/claude-ai", headers=_headers_login(user_id))

        assert _estado(client, propio) == 401
        assert _estado(client, ajeno) == 200


def test_oauth_desconectar_un_client_id_inexistente_no_falla_ni_corta_nada():
    app, user_id = _crear_app_test()
    login_headers = _headers_login(user_id)

    with TestClient(app) as client:
        access_token = _emitir_tokens_oauth(client, login_headers)["access_token"]

        res = client.delete("/api/v1/usuarios/integraciones/no-existe", headers=login_headers)

        assert res.status_code == 200
        assert res.json()["revocados"] == 0
        assert _estado(client, access_token) == 200


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


def test_oauth_consent_con_state_largo_mcp():
    """Valida que un state extenso (>1000 caracteres, ej. JWT/JWE de Google MCP) es aceptado y reflejado en el callback."""
    app, user_id = _crear_app_test()
    app.dependency_overrides[get_usuario_actual] = lambda: {
        "sub": user_id,
        "org": "org-durax",
        "rol": "ingeniero",
    }

    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    challenge = calcular_code_challenge(verifier)
    state_largo = "state_google_mcp_" + "x" * 1200

    with TestClient(app) as client:
        res = client.post(
            "/api/v1/oauth/consent",
            json={
                "client_id": "claude-ai",
                "redirect_uri": "https://claude.ai/api/mcp/oauth/callback",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "scope": "read:telemetria",
                "state": state_largo,
                "aprobado": True,
            },
        )
        assert res.status_code == 200
        redirect_url = res.json()["redirect_url"]
        assert "code=" in redirect_url
        assert f"state={state_largo}" in redirect_url
