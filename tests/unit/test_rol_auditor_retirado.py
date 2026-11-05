"""tests/unit/test_rol_auditor_retirado.py — Issue #122: el rol auditor se retira (decisión 2026-10-31).

Quedan seis roles: superadmin, admin, operador, mantenimiento, ingeniero y solo_lectura.
El registro de auditoría (/api/v1/audit/logs) queda solo para superadmin, y un token viejo
con rol auditor no obtiene ningún permiso: no escribe, no audita, no previsualiza el SGEn
y /auth/me no lo trata como usuario vigente.
"""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.application.dtos.auth_dto import ROLES_VALIDOS, MeResponseDTO
from src.application.use_cases.consultar_documentacion_sge import ROLES_PREVIEW_PERMITIDOS
from src.infrastructure.fastapi.auth_dependencies import get_auth_use_case
from src.infrastructure.fastapi.dependencies import (
    get_consultar_auditoria_use_case,
    get_usuario_actual,
    get_usuarios_repository,
    requiere_rol_auditor_o_superadmin,
    requiere_rol_escritura,
)
from src.infrastructure.fastapi.server import create_app

ROLES_VIGENTES = {"superadmin", "admin", "operador", "mantenimiento", "ingeniero", "solo_lectura"}


def test_roles_validos_son_seis_y_no_incluyen_auditor():
    assert ROLES_VALIDOS == ROLES_VIGENTES
    assert "auditor" not in ROLES_VALIDOS


def test_me_dto_rechaza_el_rol_auditor():
    with pytest.raises(ValidationError):
        MeResponseDTO(usuario="u1", rol="auditor")  # type: ignore[arg-type]


def test_guard_de_escritura_rechaza_auditor():
    with pytest.raises(HTTPException) as exc:
        requiere_rol_escritura({"usuario": "u1", "rol": "auditor"})
    assert exc.value.status_code == 403


def test_guard_de_auditoria_solo_deja_pasar_superadmin():
    claims = {"usuario": "root", "rol": "superadmin"}
    assert requiere_rol_auditor_o_superadmin(claims) == claims
    for rol in sorted(ROLES_VALIDOS - {"superadmin"} | {"auditor"}):
        with pytest.raises(HTTPException) as exc:
            requiere_rol_auditor_o_superadmin({"usuario": "u1", "rol": rol})
        assert exc.value.status_code == 403, rol


def test_previsualizacion_sge_solo_para_superadmin_y_admin():
    assert ROLES_PREVIEW_PERMITIDOS == {"superadmin", "admin"}


def test_ruta_de_auditoria_rechaza_auditor():
    app = create_app()
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "u-audit", "rol": "auditor"}
    app.dependency_overrides[get_consultar_auditoria_use_case] = lambda: MagicMock()

    response = TestClient(app).get("/api/v1/audit/logs")

    assert response.status_code == 403
    assert response.json()["detail"] == "forbidden"


def test_me_ruta_no_trata_a_un_token_auditor_como_usuario_vigente():
    from src.application.use_cases.autenticar_usuario import AutenticarUsuarioUseCase
    from src.domain.auth.services import HashContrasenaService

    repo = MagicMock()
    repo.obtener_por_id.return_value = None
    repo.obtener_por_usuario.return_value = None
    app = create_app()
    app.dependency_overrides[get_usuarios_repository] = lambda: repo
    app.dependency_overrides[get_auth_use_case] = lambda: AutenticarUsuarioUseCase(
        repo, HashContrasenaService(), MagicMock(), 480
    )
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "u-9", "usuario": "ex-auditor", "rol": "auditor"}

    response = TestClient(app).get("/api/v1/auth/me")

    assert response.status_code == 401
