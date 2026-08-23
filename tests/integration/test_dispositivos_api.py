"""Pruebas de integración de la API de dispositivos: registro de rutas y acceso protegido."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.dispositivo_dto import DispositivoResponseDTO
from src.infrastructure.fastapi.dependencies import (
    get_dispositivos_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.server import create_app


def _rutas_dispositivos(app) -> dict[str, set[str]]:
    rutas: dict[str, set[str]] = {}
    for ruta in app.routes:
        if hasattr(ruta, "methods") and hasattr(ruta, "path"):
            rutas.setdefault(ruta.path, set()).update(ruta.methods or set())
        elif hasattr(ruta, "original_router"):
            for subruta in ruta.original_router.routes:
                if hasattr(subruta, "methods") and hasattr(subruta, "path"):
                    rutas.setdefault(subruta.path, set()).update(subruta.methods or set())
    return {k: v for k, v in rutas.items() if k.startswith("/api/dispositivos")}


def test_create_app_registra_rutas_dispositivos():
    app = create_app()
    rutas = _rutas_dispositivos(app)

    assert "/api/dispositivos" in rutas
    assert "GET" in rutas["/api/dispositivos"]
    assert "POST" in rutas["/api/dispositivos"]

    assert "/api/dispositivos/{id_o_uid}" in rutas
    assert "GET" in rutas["/api/dispositivos/{id_o_uid}"]
    assert "PUT" in rutas["/api/dispositivos/{id_o_uid}"]
    assert "DELETE" in rutas["/api/dispositivos/{id_o_uid}"]


def test_listar_dispositivos_end_to_end():
    app = create_app()

    mock_dto = DispositivoResponseDTO(
        id="dev-1",
        device_uid="PM-001",
        serial_number="SN123",
        name="Tablero General",
        model="SmartPlus",
        hw_version="v2.1",
        fw_version="v1.4.2",
        tag_location="Nave A",
        is_active=True,
        status="ONLINE",
        last_seen_at=None,
        installation_type="CONSUMO",
        phases_with_ct="R,S,T",
    )

    mock_use_case = MagicMock()
    mock_use_case.listar_dispositivos.return_value = [mock_dto]

    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "user-test", "rol": "operador"}
    app.dependency_overrides[get_dispositivos_use_case] = lambda: mock_use_case

    client = TestClient(app)
    response = client.get("/api/dispositivos")

    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    data = response.json()
    assert len(data) == 1
    assert data[0]["device_uid"] == "PM-001"
