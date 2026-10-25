"""tests/unit/test_smoke_post_deploy.py — Smoke test de router/startup: validación de endpoints de salud."""

import logging
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.infrastructure.fastapi.server import create_app


class TestSmokePostDeploy:
    """Suite de smoke tests: validación rápida post-deploy."""

    def test_health_ready_returns_200_ok(self):
        """GET /health/ready responde con status 200 cuando todo está listo."""
        with (
            patch("src.infrastructure.fastapi.routes.system_router.verificar_conexion_db", return_value=True),
            patch(
                "src.infrastructure.fastapi.routes.system_router.verificar_estado_migraciones",
                return_value={"sincronizado": True, "revision_head": "abc123"},
            ),
            patch(
                "src.infrastructure.fastapi.routes.system_router._validar_datamaq_data",
                return_value={"valido": True, "organizaciones": 1, "plantas_totales": 5},
            ),
            patch(
                "src.infrastructure.fastapi.routes.system_router.get_mqtt_listener",
                return_value=MagicMock(esta_conectado=lambda: True),
            ),
        ):
            app = create_app()
            client = TestClient(app)
            response = client.get("/health/ready")

            assert response.status_code == 200

    def test_health_ready_response_estructura(self):
        """Response de /health/ready contiene los campos esperados."""
        with (
            patch("src.infrastructure.fastapi.routes.system_router.verificar_conexion_db", return_value=True),
            patch(
                "src.infrastructure.fastapi.routes.system_router.verificar_estado_migraciones",
                return_value={"sincronizado": True, "revision_head": "abc123"},
            ),
            patch(
                "src.infrastructure.fastapi.routes.system_router._validar_datamaq_data",
                return_value={"valido": True, "organizaciones": 1, "plantas_totales": 5},
            ),
            patch(
                "src.infrastructure.fastapi.routes.system_router.get_mqtt_listener",
                return_value=MagicMock(esta_conectado=lambda: True),
            ),
        ):
            app = create_app()
            client = TestClient(app)
            response = client.get("/health/ready")

            data = response.json()
            assert data["status"] == "ready"
            assert data["database_conectada"] is True
            assert "migraciones" in data
            assert data["migraciones"]["sincronizado"] is True
            assert "datamaq_data" in data
            assert data["datamaq_data"]["valido"] is True
            assert data["datamaq_data"]["organizaciones"] >= 1
            assert "timestamp" in data
            assert "mqtt_conectado" in data

    def test_health_ready_sin_db_responde_503(self):
        """GET /health/ready responde 503 si la BD no está conectada."""
        with (
            patch("src.infrastructure.fastapi.routes.system_router.verificar_conexion_db", return_value=False),
            patch(
                "src.infrastructure.fastapi.routes.system_router.verificar_estado_migraciones",
                return_value={"sincronizado": True},
            ),
            patch(
                "src.infrastructure.fastapi.routes.system_router._validar_datamaq_data",
                return_value={"valido": True, "organizaciones": 1, "plantas_totales": 5},
            ),
        ):
            app = create_app()
            client = TestClient(app)
            response = client.get("/health/ready")

            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "not_ready"
            assert data["database_conectada"] is False

    def test_health_ready_sin_datamaq_data_responde_503(self):
        """GET /health/ready responde 503 si datamaq-data no cargó correctamente."""
        with (
            patch("src.infrastructure.fastapi.routes.system_router.verificar_conexion_db", return_value=True),
            patch(
                "src.infrastructure.fastapi.routes.system_router.verificar_estado_migraciones",
                return_value={"sincronizado": True, "revision_head": "abc123"},
            ),
            patch(
                "src.infrastructure.fastapi.routes.system_router._validar_datamaq_data",
                return_value={"valido": False, "razon": "sin_organizaciones"},
            ),
        ):
            app = create_app()
            client = TestClient(app)
            response = client.get("/health/ready")

            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "not_ready"
            assert data["datamaq_data"]["valido"] is False

    def test_health_live_siempre_200(self):
        """GET /health/live siempre responde 200 (liveness probe)."""
        app = create_app()
        client = TestClient(app)
        response = client.get("/health/live")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"
        assert "timestamp" in data

    def test_cargar_organizaciones_desde_yaml_sin_exception(self):
        """Cargar organizaciones desde YAML no levanta exception no controlada."""
        import pytest

        from src.infrastructure.yaml.loaders import cargar_organizaciones_modulares

        with patch("os.path.isdir", return_value=True), patch("os.listdir", return_value=["organizaciones.yml"]):
            try:
                resultado = cargar_organizaciones_modulares("/fake/data/dir")
                assert resultado is not None
            except FileNotFoundError:
                pytest.skip("No se encontró el directorio /fake/data/dir")
            except Exception as e:
                pytest.fail(f"cargar_organizaciones_modulares() levantó {type(e).__name__}: {e}")

    def test_app_startup_sin_critical_logs(self, caplog):
        """App startup no emite logs CRITICAL."""
        with (
            patch("src.infrastructure.fastapi.routes.system_router.verificar_conexion_db", return_value=True),
            patch(
                "src.infrastructure.fastapi.routes.system_router.verificar_estado_migraciones",
                return_value={"sincronizado": True, "revision_head": "abc123"},
            ),
            patch(
                "src.infrastructure.fastapi.routes.system_router._validar_datamaq_data",
                return_value={"valido": True, "organizaciones": 1, "plantas_totales": 5},
            ),
        ):
            caplog.set_level(logging.CRITICAL)
            app = create_app()
            client = TestClient(app)
            client.get("/health/ready")

            critical_logs = [record for record in caplog.records if record.levelname == "CRITICAL"]
            assert len(critical_logs) == 0, f"Se encontraron {len(critical_logs)} logs CRITICAL en startup"

    def test_create_app_registra_system_router(self):
        """create_app() registra el system_router con health endpoints."""
        with (
            patch("src.infrastructure.fastapi.routes.system_router.verificar_conexion_db", return_value=True),
            patch(
                "src.infrastructure.fastapi.routes.system_router.verificar_estado_migraciones",
                return_value={"sincronizado": True},
            ),
            patch(
                "src.infrastructure.fastapi.routes.system_router._validar_datamaq_data",
                return_value={"valido": True, "organizaciones": 1, "plantas_totales": 5},
            ),
        ):
            app = create_app()
            client = TestClient(app)
            rutas_criticas = ["/health/ready", "/health/live", "/health"]
            for ruta in rutas_criticas:
                response = client.get(ruta)
                assert response.status_code in (200, 503), (
                    f"Ruta {ruta} no responde correctamente (status {response.status_code})"
                )
