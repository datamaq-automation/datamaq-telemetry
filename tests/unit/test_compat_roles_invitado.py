"""Compatibilidad temporal de los roles invitado e invitado_global (TODO #65).

La traducción vive en el adaptador (infrastructure/fastapi). Estos tests fijan que:
- /me devuelve el rol real del token, y el caso de uso recibe el placeholder.
- El 2FA queda bloqueado para los roles de compatibilidad.
- Los roles de compatibilidad no escriben ni tienen acceso global.
- El dominio y la aplicación no mencionan el rol.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.application.dtos.auth_dto import MeResponseDTO
from src.domain.auth.services import ROLES_ACCESO_GLOBAL
from src.infrastructure.fastapi.auth_dependencies import get_auth_use_case
from src.infrastructure.fastapi.dependencies import (
    ROL_PLACEHOLDER_ME,
    get_usuario_actual,
    requiere_rol_escritura,
)
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.settings.config import Settings

ROLES_COMPAT = ("invitado", "invitado_global")
RAIZ = Path(__file__).resolve().parents[2]


def _cliente(claims: dict):
    settings = Settings(APP_ENV="development", DEBUG=True, API_SECRET_KEY="dev-secret-key-12345", CORS_ORIGINS="")
    mock_uc = MagicMock()
    mock_uc.me.side_effect = lambda c: MeResponseDTO(usuario=c.get("usuario", "u1"), rol=c["rol"])
    app = create_app(settings=settings)
    app.dependency_overrides[get_usuario_actual] = lambda: claims
    app.dependency_overrides[get_auth_use_case] = lambda: mock_uc
    return TestClient(app), mock_uc


@pytest.mark.parametrize("rol", ROLES_COMPAT)
def test_me_devuelve_el_rol_real_del_token(rol):
    client, _ = _cliente({"usuario": "u1", "sub": "u1", "rol": rol})
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.json()["rol"] == rol


@pytest.mark.parametrize("rol", ROLES_COMPAT)
def test_caso_de_uso_recibe_el_placeholder_no_el_rol_retirado(rol):
    client, mock_uc = _cliente({"usuario": "u1", "sub": "u1", "rol": rol})
    client.get("/api/v1/auth/me")
    recibido = mock_uc.me.call_args.args[0]
    assert recibido["rol"] == ROL_PLACEHOLDER_ME
    assert recibido["rol"] not in ROLES_COMPAT


@pytest.mark.parametrize("rol", ROLES_COMPAT)
def test_2fa_bloqueado_para_roles_de_compatibilidad(rol):
    client, _ = _cliente({"usuario": "u1", "sub": "u1", "rol": rol})
    response = client.post("/api/v1/auth/2fa/setup")
    assert response.status_code == 403
    assert response.json()["detail"] == "2fa_no_disponible_para_invitado"


@pytest.mark.parametrize("rol", ROLES_COMPAT)
def test_rol_de_compatibilidad_no_escribe(rol):
    with pytest.raises(HTTPException) as exc:
        requiere_rol_escritura({"usuario": "u1", "rol": rol})
    assert exc.value.status_code == 403


@pytest.mark.parametrize("rol", ROLES_COMPAT)
def test_rol_de_compatibilidad_no_tiene_acceso_global(rol):
    assert rol not in ROLES_ACCESO_GLOBAL


def test_dominio_y_aplicacion_no_mencionan_el_rol_retirado():
    hallazgos = []
    for carpeta in ("src/domain", "src/application"):
        for archivo in (RAIZ / carpeta).rglob("*.py"):
            texto = archivo.read_text(encoding="utf-8")
            if "invitado" in texto:
                hallazgos.append(str(archivo.relative_to(RAIZ)))
    assert hallazgos == []
