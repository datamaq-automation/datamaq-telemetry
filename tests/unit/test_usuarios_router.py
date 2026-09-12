"""tests/unit/test_usuarios_router.py — Tests unitarios para el endpoint POST /api/v1/usuarios."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.infrastructure.fastapi.dependencies import get_usuario_actual
from src.infrastructure.fastapi.server import create_app


def _cliente(rol: str = "admin", org: str = "org-1") -> tuple[TestClient, MagicMock]:
    app = create_app()
    mock_repo = MagicMock()
    app.dependency_overrides[get_usuario_actual] = lambda: {
        "sub": "usuario-admin",
        "rol": rol,
        "org": org,
    }
    # Mocking repo via dependency override if applicable or patching
    return TestClient(app), mock_repo


def test_crear_usuario_exitoso_como_admin():
    app = create_app()
    mock_repo_users = MagicMock()
    mock_repo_users.obtener_por_usuario.return_value = None
    mock_repo_users.guardar.side_effect = lambda u: u

    app.dependency_overrides[get_usuario_actual] = lambda: {
        "sub": "usuario-admin",
        "rol": "admin",
        "org": "org-1",
    }
    from src.infrastructure.fastapi.dependencies import get_usuarios_repository

    app.dependency_overrides[get_usuarios_repository] = lambda: mock_repo_users

    client = TestClient(app)

    payload = {
        "usuario": "tecnico_1",
        "rol": "operador",
    }

    response = client.post("/api/v1/usuarios", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["usuario"] == "tecnico_1"
    assert data["rol"] == "operador"
    assert data["organizacion_id"] == "org-1"
    assert data["esta_activo"] is True
    mock_repo_users.guardar.assert_called_once()


def test_crear_usuario_rol_operador_rechazado_403():
    app = create_app()
    app.dependency_overrides[get_usuario_actual] = lambda: {
        "sub": "usuario-operador",
        "rol": "operador",
        "org": "org-1",
    }

    client = TestClient(app)

    payload = {
        "usuario": "tecnico_2",
        "rol": "operador",
    }

    response = client.post("/api/v1/usuarios", json=payload)
    assert response.status_code == 403
