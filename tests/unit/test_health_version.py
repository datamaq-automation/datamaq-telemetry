"""tests/unit/test_health_version.py — Pruebas unitarias para /health y /version."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.infrastructure.fastapi.server import create_app
from src.infrastructure.settings.config import get_settings
from src.version import __version__


def test_health_check_incluye_version_commit_despliegue_y_servicios():
    app = create_app(get_settings())
    client = TestClient(app)

    with (
        patch("src.infrastructure.fastapi.routes.system_router.verificar_conexion_db", return_value=True),
        patch(
            "src.infrastructure.fastapi.routes.system_router.verificar_estado_migraciones",
            return_value={"sincronizado": True},
        ),
        patch("src.infrastructure.fastapi.routes.system_router._validar_datamaq_data", return_value={"valido": True}),
        patch("src.infrastructure.fastapi.routes.system_router.get_mqtt_listener") as mock_listener,
    ):
        mock_mqtt = MagicMock()
        mock_mqtt.esta_conectado.return_value = True
        mock_listener.return_value = mock_mqtt

        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()

        assert data["version"] == __version__
        assert "commit" in data
        assert "fecha_despliegue" in data
        assert data["mysql_conectado"] is True
        assert data["mqtt_conectado"] is True
        assert data["status"] == "ready"


def test_health_check_falla_si_mysql_desconectado():
    app = create_app(get_settings())
    client = TestClient(app)

    with (
        patch("src.infrastructure.fastapi.routes.system_router.verificar_conexion_db", return_value=False),
        patch(
            "src.infrastructure.fastapi.routes.system_router.verificar_estado_migraciones",
            return_value={"sincronizado": False},
        ),
        patch("src.infrastructure.fastapi.routes.system_router._validar_datamaq_data", return_value={"valido": True}),
        patch("src.infrastructure.fastapi.routes.system_router.get_mqtt_listener") as mock_listener,
    ):
        mock_mqtt = MagicMock()
        mock_mqtt.esta_conectado.return_value = False
        mock_listener.return_value = mock_mqtt

        resp = client.get("/health")
        assert resp.status_code == 503
        data = resp.json()

        assert data["version"] == __version__
        assert data["mysql_conectado"] is False
        assert data["mqtt_conectado"] is False
        assert data["status"] == "not_ready"


def test_version_endpoint():
    app = create_app(get_settings())
    client = TestClient(app)

    with (
        patch("src.infrastructure.fastapi.routes.system_router.verificar_conexion_db", return_value=True),
        patch("src.infrastructure.fastapi.routes.system_router.get_mqtt_listener") as mock_listener,
    ):
        mock_mqtt = MagicMock()
        mock_mqtt.esta_conectado.return_value = True
        mock_listener.return_value = mock_mqtt

        resp = client.get("/version")
        assert resp.status_code == 200
        data = resp.json()

        assert data["version"] == __version__
        assert "commit" in data
        assert "fecha_despliegue" in data
        assert data["mysql_conectado"] is True
        assert data["mqtt_conectado"] is True
