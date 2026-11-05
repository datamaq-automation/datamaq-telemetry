"""tests/unit/test_admin_router.py — Tests unitarios para admin_router (paginación auditoría TI)."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.infrastructure.fastapi.dependencies import (
    get_usuario_actual,
    requiere_rol_admin,
)
from src.infrastructure.fastapi.dependencies_auditoria_ti import get_consultar_auditoria_cambios_ti
from src.infrastructure.fastapi.server import create_app


def _cliente_admin():
    app = create_app()
    mock_auditoria = MagicMock()
    app.dependency_overrides[get_usuario_actual] = lambda: {
        "sub": "admin-1",
        "rol": "admin",
        "org": "org-1",
    }
    app.dependency_overrides[requiere_rol_admin] = lambda: {
        "sub": "admin-1",
        "rol": "admin",
        "org": "org-1",
    }
    app.dependency_overrides[get_consultar_auditoria_cambios_ti] = lambda: mock_auditoria
    return TestClient(app), mock_auditoria


def test_listar_cambios_ti_paginacion_por_defecto():
    client, mock_auditoria = _cliente_admin()
    mock_auditoria.listar.return_value = []

    response = client.get("/api/v1/admin/auditoria/cambios-ti")

    assert response.status_code == 200
    mock_auditoria.listar.assert_called_once()
    kwargs = mock_auditoria.listar.call_args.kwargs
    assert kwargs["limite"] == 50
    assert kwargs["offset"] == 0


def test_listar_cambios_ti_paginacion_custom():
    client, mock_auditoria = _cliente_admin()
    mock_auditoria.listar.return_value = []

    response = client.get("/api/v1/admin/auditoria/cambios-ti?limite=20&offset=40")

    assert response.status_code == 200
    kwargs = mock_auditoria.listar.call_args.kwargs
    assert kwargs["limite"] == 20
    assert kwargs["offset"] == 40


def test_listar_cambios_ti_limite_invalido_retorna_422():
    client, _ = _cliente_admin()

    # limite < 1
    resp_bajo = client.get("/api/v1/admin/auditoria/cambios-ti?limite=0")
    assert resp_bajo.status_code == 422

    # limite > 500
    resp_alto = client.get("/api/v1/admin/auditoria/cambios-ti?limite=501")
    assert resp_alto.status_code == 422


def test_listar_cambios_ti_offset_negativo_retorna_422():
    client, _ = _cliente_admin()

    resp = client.get("/api/v1/admin/auditoria/cambios-ti?offset=-5")
    assert resp.status_code == 422
