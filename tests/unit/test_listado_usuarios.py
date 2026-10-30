"""tests/unit/test_listado_usuarios.py — Listado global de cuentas, solo lectura (issue #102)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.application.use_cases.listar_usuarios import ListarUsuariosUseCase
from src.domain.auth.services import puede_listar_usuarios
from src.infrastructure.fastapi import dependencies as deps
from src.infrastructure.fastapi.dependencies import get_usuario_actual, get_usuarios_repository
from src.infrastructure.fastapi.server import create_app


def _usuario(id_: str, usuario: str, rol: str, org: str | None) -> MagicMock:
    u = MagicMock()
    u.id = id_
    u.usuario = usuario
    u.rol = rol
    u.organizacion_id = org
    u.esta_activo = True
    u.hash_contrasena = "secreto"
    return u


def _cliente(rol: str, listado_operador: bool, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, MagicMock]:
    monkeypatch.setattr(deps, "get_settings", lambda: SimpleNamespace(LISTADO_USUARIOS_OPERADOR=listado_operador))
    app = create_app()
    repo = MagicMock()
    repo.listar_todos.return_value = [
        _usuario("u1", "ana@x.com", "admin", "org-1"),
        _usuario("u2", "bruno@y.com", "operador", "org-2"),
        _usuario("u3", "root@z.com", "superadmin", None),
    ]
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "quien", "rol": rol, "org": "org-1"}
    app.dependency_overrides[get_usuarios_repository] = lambda: repo
    return TestClient(app), repo


# --- Política de dominio ---


@pytest.mark.parametrize("rol", ["superadmin", "admin"])
def test_admin_y_superadmin_siempre_listan(rol: str) -> None:
    assert puede_listar_usuarios(rol, listado_operador_habilitado=False) is True


def test_operador_no_lista_con_flag_apagado() -> None:
    assert puede_listar_usuarios("operador", listado_operador_habilitado=False) is False


def test_operador_lista_solo_con_flag_encendido() -> None:
    assert puede_listar_usuarios("operador", listado_operador_habilitado=True) is True


@pytest.mark.parametrize("rol", ["mantenimiento", "ingeniero", "auditor", "solo_lectura", "invitado", ""])
def test_otros_roles_no_listan_aunque_flag_encendido(rol: str) -> None:
    assert puede_listar_usuarios(rol, listado_operador_habilitado=True) is False


# --- Caso de uso ---


def test_caso_de_uso_devuelve_todas_las_filas_sin_escribir() -> None:
    repo = MagicMock()
    repo.listar_todos.return_value = [_usuario("u1", "ana@x.com", "admin", "org-1")]

    filas = ListarUsuariosUseCase(repo).ejecutar()

    assert [f.usuario for f in filas] == ["ana@x.com"]
    assert filas[0].organizacion_id == "org-1"
    repo.guardar.assert_not_called()


def test_dto_no_expone_hash_ni_secretos() -> None:
    repo = MagicMock()
    repo.listar_todos.return_value = [_usuario("u1", "ana@x.com", "admin", "org-1")]

    dump = ListarUsuariosUseCase(repo).ejecutar()[0].model_dump()

    assert set(dump) == {"id", "usuario", "rol", "organizacion_id", "esta_activo"}


# --- Ruta GET /api/v1/usuarios ---


def test_operador_recibe_403_con_flag_apagado(monkeypatch: pytest.MonkeyPatch) -> None:
    client, repo = _cliente("operador", False, monkeypatch)

    assert client.get("/api/v1/usuarios").status_code == 403
    repo.listar_todos.assert_not_called()


def test_operador_lista_con_flag_encendido_sin_secretos(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _cliente("operador", True, monkeypatch)

    respuesta = client.get("/api/v1/usuarios")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert [f["usuario"] for f in cuerpo] == ["ana@x.com", "bruno@y.com", "root@z.com"]
    assert all("hash_contrasena" not in f for f in cuerpo)


def test_admin_lista_sin_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _cliente("admin", False, monkeypatch)

    assert client.get("/api/v1/usuarios").status_code == 200


def test_operador_sigue_sin_alta_aunque_liste(monkeypatch: pytest.MonkeyPatch) -> None:
    client, repo = _cliente("operador", True, monkeypatch)

    respuesta = client.post("/api/v1/usuarios", json={"usuario": "nuevo_1", "rol": "operador"})

    assert respuesta.status_code == 403
    repo.guardar.assert_not_called()


def test_operador_sigue_sin_baja_ni_cambio_de_rol(monkeypatch: pytest.MonkeyPatch) -> None:
    client, repo = _cliente("operador", True, monkeypatch)

    assert client.delete("/api/v1/usuarios/u1").status_code == 403
    assert client.patch("/api/v1/usuarios/u1/rol", json={"rol": "admin"}).status_code == 403
    repo.guardar.assert_not_called()
