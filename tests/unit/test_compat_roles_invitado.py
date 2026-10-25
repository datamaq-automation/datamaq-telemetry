"""Compatibilidad temporal de los roles invitado e invitado_global (TODO #65).

Un token legacy en /me no obtiene ningún permiso. Estos tests fijan la regla por permiso
(escritura, admin, superadmin, 2FA, acceso global, plantas, organización) y que el módulo de
compatibilidad no use ningún rol vigente como placeholder.
"""

import ast
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.domain.auth.services import ROLES_ACCESO_GLOBAL
from src.infrastructure.fastapi.auth_dependencies import get_auth_use_case
from src.infrastructure.fastapi.compat_roles_invitado import ROLES_COMPAT_CLIENTE
from src.infrastructure.fastapi.dependencies import (
    get_usuario_actual,
    get_usuarios_repository,
    requiere_rol_admin,
    requiere_rol_auditor_o_superadmin,
    requiere_rol_escritura,
    requiere_rol_superadmin,
)
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.settings.config import Settings

RAIZ = Path(__file__).resolve().parents[2]
MODULO_COMPAT = RAIZ / "src/infrastructure/fastapi/compat_roles_invitado.py"
ROLES_LEGACY = sorted(ROLES_COMPAT_CLIENTE)


def _cliente(claims: dict):
    settings = Settings(APP_ENV="development", DEBUG=True, API_SECRET_KEY="dev-secret-key-12345", CORS_ORIGINS="")
    mock_uc = MagicMock()
    repo = MagicMock()
    repo.obtener_por_id.return_value = None
    repo.obtener_por_usuario.return_value = None
    app = create_app(settings=settings)
    app.dependency_overrides[get_usuario_actual] = lambda: claims
    app.dependency_overrides[get_auth_use_case] = lambda: mock_uc
    app.dependency_overrides[get_usuarios_repository] = lambda: repo
    return TestClient(app), mock_uc


@pytest.mark.parametrize("rol", ROLES_LEGACY)
def test_me_devuelve_el_rol_legacy_sin_consultar_el_caso_de_uso(rol):
    client, mock_uc = _cliente({"usuario": "u1", "sub": "u1", "rol": rol})
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.json()["rol"] == rol
    mock_uc.me.assert_not_called()


@pytest.mark.parametrize("rol", ROLES_LEGACY)
def test_me_legacy_no_concede_plantas_ni_organizacion(rol):
    client, _ = _cliente({"usuario": "u1", "sub": "u1", "rol": rol, "org": "org-a"})
    datos = client.get("/api/v1/auth/me").json()
    assert datos["plantas"] == []
    assert datos["organizacion_id"] is None


@pytest.mark.parametrize("rol", ROLES_LEGACY)
@pytest.mark.parametrize(
    "guard", [requiere_rol_escritura, requiere_rol_admin, requiere_rol_superadmin, requiere_rol_auditor_o_superadmin]
)
def test_legacy_no_pasa_guards_de_rol(rol, guard):
    with pytest.raises(HTTPException) as exc:
        guard({"usuario": "u1", "rol": rol})
    assert exc.value.status_code == 403


@pytest.mark.parametrize("rol", ROLES_LEGACY)
@pytest.mark.parametrize("ruta", ["/api/v1/auth/2fa/setup", "/api/v1/auth/2fa/activar", "/api/v1/auth/2fa/desactivar"])
def test_legacy_no_puede_usar_2fa(rol, ruta):
    client, _ = _cliente({"usuario": "u1", "sub": "u1", "rol": rol})
    response = client.post(ruta)
    assert response.status_code == 403
    assert response.json()["detail"] == "2fa_no_disponible_para_invitado"


@pytest.mark.parametrize("rol", ROLES_LEGACY)
def test_legacy_no_tiene_acceso_global(rol):
    assert rol not in ROLES_ACCESO_GLOBAL


def test_modulo_de_compatibilidad_no_usa_roles_vigentes_como_placeholder():
    # Roles vigentes: los de ROLES_VALIDOS menos los de compatibilidad (los que da el dominio).
    from src.application.use_cases.autenticar_usuario import ROLES_VALIDOS

    vigentes = set(ROLES_VALIDOS) - set(ROLES_COMPAT_CLIENTE)
    arbol = ast.parse(MODULO_COMPAT.read_text(encoding="utf-8"))
    literales = {
        nodo.value for nodo in ast.walk(arbol) if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str)
    }
    assert vigentes.isdisjoint(literales), f"Rol vigente usado en el módulo de compat: {vigentes & literales}"
