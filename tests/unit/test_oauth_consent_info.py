"""tests/unit/test_oauth_consent_info.py — consent-info sin datos fabricados (Issue #54, H-C y H-F).

La planta activa sale del mismo criterio que /auth/me (primera planta permitida al usuario). Sin plantas,
los campos van en null: nunca un nombre inventado. Un scope desconocido responde invalid_scope, no una descripción.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.application.dtos.auth_dto import PlantaAccesoDTO
from src.domain.oauth.entities import OAuthClient
from src.infrastructure.fastapi.auth_dependencies import get_acceso_plantas_use_case
from src.infrastructure.fastapi.dependencies import get_oauth_repository, get_usuario_actual
from src.infrastructure.fastapi.server import create_app

REDIRECT = "https://claude.ai/api/mcp/oauth/callback"
CHALLENGE = "a" * 43


def _cliente(claims: dict, plantas: list[PlantaAccesoDTO]):
    app = create_app()
    repo = MagicMock()
    repo.obtener_cliente.return_value = OAuthClient(
        client_id="claude-ai",
        client_name="Claude (Anthropic)",
        redirect_uris=(REDIRECT,),
        created_at=datetime.now(timezone.utc),
    )
    acceso = MagicMock()
    acceso.resolver.return_value = plantas
    app.dependency_overrides[get_usuario_actual] = lambda: claims
    app.dependency_overrides[get_oauth_repository] = lambda: repo
    app.dependency_overrides[get_acceso_plantas_use_case] = lambda: acceso
    return TestClient(app), repo, acceso


PLANTAS_ORG = [
    PlantaAccesoDTO(id="planta-a", nombre="Planta A", organizacion_id="org-001", puede_cambiar=True),
    PlantaAccesoDTO(id="planta-b", nombre="Planta B", organizacion_id="org-001", puede_cambiar=False),
]


def test_planta_activa_es_la_primera_permitida_al_usuario():
    client, _, acceso = _cliente({"sub": "usr-1", "rol": "admin", "org": "org-001"}, PLANTAS_ORG)

    res = client.get("/api/v1/oauth/consent-info?client_id=claude-ai&scope=read:telemetria")

    assert res.status_code == 200
    data = res.json()
    assert data["planta_activa_id"] == "planta-a"
    assert data["planta_activa_nombre"] == "Planta A"
    acceso.resolver.assert_called_once_with("usr-1", "admin", "org-001")


def test_sin_plantas_permitidas_los_campos_de_planta_van_en_null():
    client, _, _ = _cliente({"sub": "usr-1", "rol": "admin"}, [])

    data = client.get("/api/v1/oauth/consent-info?client_id=claude-ai").json()

    assert data["planta_activa_id"] is None
    assert data["planta_activa_nombre"] is None
    assert "Planta Principal" not in str(data)


def test_scope_desconocido_se_descarta_y_no_se_describe_como_lectura():
    client, _, _ = _cliente({"sub": "usr-1", "rol": "admin", "org": "org-001"}, PLANTAS_ORG)

    res = client.get("/api/v1/oauth/consent-info?client_id=claude-ai&scope=read:alertas read:todo")

    assert res.status_code == 200
    assert [s["scope"] for s in res.json()["scopes"]] == ["read:alertas"]
    assert "Acceso de lectura autorizado" not in res.text


def test_solo_scopes_desconocidos_muestra_los_defaults():
    client, _, _ = _cliente({"sub": "usr-1", "rol": "admin", "org": "org-001"}, PLANTAS_ORG)

    res = client.get("/api/v1/oauth/consent-info?client_id=claude-ai&scope=read:todo")

    assert res.status_code == 200
    assert [s["scope"] for s in res.json()["scopes"]] == [
        "read:telemetria",
        "read:analitica",
        "read:alertas",
    ]
    assert "Acceso de lectura autorizado" not in res.text


def test_scopes_validos_muestran_su_descripcion_conocida():
    client, _, _ = _cliente({"sub": "usr-1", "rol": "admin", "org": "org-001"}, PLANTAS_ORG)

    data = client.get("/api/v1/oauth/consent-info?client_id=claude-ai&scope=read:alertas").json()

    assert data["scopes"] == [
        {"scope": "read:alertas", "descripcion": "Monitoreo y consulta de alertas operativas"},
    ]


def test_consent_con_scope_desconocido_emite_con_la_interseccion():
    client, repo, _ = _cliente({"sub": "usr-1", "rol": "admin", "org": "org-001"}, PLANTAS_ORG)

    res = client.post(
        "/api/v1/oauth/consent",
        json={
            "client_id": "claude-ai",
            "redirect_uri": REDIRECT,
            "code_challenge": CHALLENGE,
            "scope": "read:alertas read:todo",
            "aprobado": True,
        },
    )

    assert res.status_code == 200
    assert res.json()["redirect_url"].startswith(REDIRECT + "?code=")
    assert repo.guardar_codigo.call_args.args[0].scope == "read:alertas"


@pytest.mark.parametrize("scope", ["read:telemetria", "read:analitica read:alertas"])
def test_consent_con_scope_valido_sigue_emitiendo_redirect(scope):
    client, repo, _ = _cliente({"sub": "usr-1", "rol": "admin", "org": "org-001"}, PLANTAS_ORG)

    res = client.post(
        "/api/v1/oauth/consent",
        json={
            "client_id": "claude-ai",
            "redirect_uri": REDIRECT,
            "code_challenge": CHALLENGE,
            "scope": scope,
            "aprobado": True,
        },
    )

    assert res.status_code == 200
    assert res.json()["redirect_url"].startswith(REDIRECT + "?code=")
    repo.guardar_codigo.assert_called_once()
