"""tests/unit/test_oauth_consent_rol_escritura.py — Issue #99, decisión 2026-10-31 (oauth-consent-rol-escritura).

El consentimiento y la autorización OAuth emiten un código para una integración: son escrituras de
integración y exigen rol de escritura explícito. Solo lectura recibe 403; un rol operativo pasa.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.domain.oauth.entities import OAuthClient
from src.infrastructure.fastapi.dependencies import get_oauth_repository, get_usuario_actual
from src.infrastructure.fastapi.server import create_app

REDIRECT = "https://claude.ai/api/mcp/oauth/callback"
CHALLENGE = "a" * 43


def _cliente(rol: str) -> tuple[TestClient, MagicMock]:
    app = create_app()
    repo = MagicMock()
    repo.obtener_cliente.return_value = OAuthClient(
        client_id="claude-ai",
        client_name="Claude (Anthropic)",
        redirect_uris=(REDIRECT,),
        created_at=datetime.now(timezone.utc),
    )
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "usr-1", "rol": rol, "org": "org-001"}
    app.dependency_overrides[get_oauth_repository] = lambda: repo
    return TestClient(app), repo


def test_consent_sin_rol_de_escritura_responde_403():
    client, repo = _cliente("solo_lectura")

    respuesta = client.post(
        "/api/v1/oauth/consent",
        json={
            "client_id": "claude-ai",
            "redirect_uri": REDIRECT,
            "code_challenge": CHALLENGE,
            "scope": "read:alertas",
            "aprobado": True,
        },
    )

    assert respuesta.status_code == 403
    assert respuesta.json()["detail"] == "forbidden"
    repo.guardar_codigo.assert_not_called()


def test_consent_con_rol_operativo_pasa():
    client, repo = _cliente("operador")

    respuesta = client.post(
        "/api/v1/oauth/consent",
        json={
            "client_id": "claude-ai",
            "redirect_uri": REDIRECT,
            "code_challenge": CHALLENGE,
            "scope": "read:alertas",
            "aprobado": True,
        },
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["redirect_url"].startswith(REDIRECT + "?code=")
    repo.guardar_codigo.assert_called_once()


def test_authorize_sin_rol_de_escritura_responde_403():
    client, repo = _cliente("solo_lectura")

    respuesta = client.post(
        "/api/v1/oauth/authorize",
        json={
            "client_id": "claude-ai",
            "redirect_uri": REDIRECT,
            "code_challenge": CHALLENGE,
            "scope": "read:alertas",
        },
    )

    assert respuesta.status_code == 403
    assert respuesta.json()["detail"] == "forbidden"
    repo.guardar_codigo.assert_not_called()


def test_authorize_con_rol_operativo_pasa():
    client, repo = _cliente("operador")

    respuesta = client.post(
        "/api/v1/oauth/authorize",
        json={
            "client_id": "claude-ai",
            "redirect_uri": REDIRECT,
            "code_challenge": CHALLENGE,
            "scope": "read:alertas",
        },
    )

    assert respuesta.status_code == 200
    assert "code" in respuesta.json()
    repo.guardar_codigo.assert_called_once()
