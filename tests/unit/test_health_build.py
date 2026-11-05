"""tests/unit/test_health_build.py — Pruebas unitarias del endpoint GET /health/build (#79)."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.infrastructure.fastapi.server import create_app
from src.infrastructure.settings.config import Settings, get_settings


@pytest.fixture
def app_with_build_file(tmp_path: Path):
    """Fixture que permite configurar la ruta de build_info.json vía dependency override."""
    app = create_app()

    def _configurar(contenido: str | None = None, dict_data: dict | None = None):
        build_file = tmp_path / "build_info.json"
        if dict_data is not None:
            build_file.write_text(json.dumps(dict_data), encoding="utf-8")
        elif contenido is not None:
            build_file.write_text(contenido, encoding="utf-8")

        test_settings = Settings(BUILD_INFO_PATH=str(build_file))
        app.dependency_overrides[get_settings] = lambda: test_settings
        return TestClient(app)

    yield _configurar
    app.dependency_overrides.clear()


def test_health_build_con_archivo_valido(app_with_build_file):
    """GET /health/build retorna commit de 7 caracteres y rama cuando el archivo es válido."""
    client = app_with_build_file(dict_data={"commit": "3ab7276", "rama": "main"})
    response = client.get("/health/build")

    assert response.status_code == 200
    assert response.json() == {"commit": "3ab7276", "rama": "main"}


def test_health_build_commit_sha_largo_truncado_a_7_caracteres(app_with_build_file):
    """GET /health/build trunca el hash del commit a exactamente 7 caracteres."""
    client = app_with_build_file(dict_data={"commit": "3ab7276a0e4abdb8c2252584ef9defcda56e236a", "rama": "develop"})
    response = client.get("/health/build")

    assert response.status_code == 200
    assert response.json() == {"commit": "3ab7276", "rama": "develop"}


def test_health_build_sin_archivo_devuelve_desconocido(app_with_build_file):
    """GET /health/build responde HTTP 200 con 'desconocido' si el archivo no existe."""
    client = app_with_build_file()  # Sin crear el archivo
    response = client.get("/health/build")

    assert response.status_code == 200
    assert response.json() == {"commit": "desconocido", "rama": "desconocido"}


def test_health_build_json_invalido_devuelve_desconocido(app_with_build_file):
    """GET /health/build responde HTTP 200 con 'desconocido' ante JSON corrupto/inválido."""
    client = app_with_build_file(contenido="esto no es un json válido {")
    response = client.get("/health/build")

    assert response.status_code == 200
    assert response.json() == {"commit": "desconocido", "rama": "desconocido"}


def test_health_build_no_contiene_campos_extra_ni_entorno(app_with_build_file):
    """Response de /health/build contiene únicamente los campos 'commit' y 'rama' (sin entorno ni extras)."""
    client = app_with_build_file(
        dict_data={
            "commit": "3ab7276",
            "rama": "main",
            "entorno": "production",
            "app_env": "production",
            "secreto": "no_revelar",
            "extra": 12345,
        }
    )
    response = client.get("/health/build")

    assert response.status_code == 200
    datos = response.json()
    assert set(datos.keys()) == {"commit", "rama"}
    assert "entorno" not in datos
    assert "app_env" not in datos
    assert "secreto" not in datos


def test_health_build_sin_autenticacion(app_with_build_file):
    """GET /health/build es un endpoint público que no requiere headers de auth ni cookies."""
    client = app_with_build_file(dict_data={"commit": "abcdef1", "rama": "staging"})
    # Petición completamente sin credenciales
    response = client.get("/health/build")

    assert response.status_code == 200
    assert response.json()["commit"] == "abcdef1"


def test_health_build_campos_vacios_o_nulos(app_with_build_file):
    """Campos vacíos o nulos en el JSON devuelven 'desconocido'."""
    client = app_with_build_file(dict_data={"commit": "", "rama": None})
    response = client.get("/health/build")

    assert response.status_code == 200
    assert response.json() == {"commit": "desconocido", "rama": "desconocido"}
