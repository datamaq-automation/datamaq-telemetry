"""Pruebas de integración de la API de telemetría: registro de rutas, ejecución end-to-end y serialización DTO."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.telemetria_dto import (
    LecturaInstantaneaDTO,
    TelemetriaLatestResponseDTO,
)
from src.infrastructure.fastapi.dependencies import (
    get_telemetria_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.server import create_app


def _rutas_telemetria(app) -> dict[str, set[str]]:
    rutas: dict[str, set[str]] = {}
    for ruta in app.routes:
        if hasattr(ruta, "methods") and hasattr(ruta, "path"):
            rutas.setdefault(ruta.path, set()).update(ruta.methods or set())
        elif hasattr(ruta, "original_router"):
            for subruta in ruta.original_router.routes:
                if hasattr(subruta, "methods") and hasattr(subruta, "path"):
                    rutas.setdefault(subruta.path, set()).update(subruta.methods or set())
    return {k: v for k, v in rutas.items() if k.startswith("/api/telemetria")}


def test_create_app_registra_rutas_telemetria():
    app = create_app()
    rutas = _rutas_telemetria(app)

    assert "/api/telemetria/latest/{device_id}" in rutas
    assert "GET" in rutas["/api/telemetria/latest/{device_id}"]

    assert "/api/telemetria/instantaneous/{device_id}" in rutas
    assert "GET" in rutas["/api/telemetria/instantaneous/{device_id}"]

    assert "/api/telemetria/energy/{device_id}" in rutas
    assert "GET" in rutas["/api/telemetria/energy/{device_id}"]

    assert "/api/telemetria/alerts/{device_id}" in rutas
    assert "GET" in rutas["/api/telemetria/alerts/{device_id}"]


def test_get_latest_telemetry_end_to_end_con_thd():
    app = create_app()

    ahora = datetime.now(timezone.utc)
    mock_dto = TelemetriaLatestResponseDTO(
        device_id="dev-test-1",
        device_name="Medidor Principal",
        device_status="ONLINE",
        last_seen_at=ahora,
        instantanea=LecturaInstantaneaDTO(
            recorded_at=ahora,
            voltage_r=Decimal("220.5"),
            voltage_s=Decimal("221.0"),
            voltage_t=Decimal("219.8"),
            current_r=Decimal("10.2"),
            current_s=Decimal("9.8"),
            current_t=Decimal("10.5"),
            active_power_r=Decimal("2249.1"),
            active_power_s=Decimal("2165.8"),
            active_power_t=Decimal("2307.9"),
            total_active_power=Decimal("6722.8"),
            thd_v_r=Decimal("1.85"),
            thd_i_r=Decimal("3.42"),
            thd_v_s=Decimal("1.90"),
            thd_i_s=Decimal("3.50"),
            thd_v_t=Decimal("1.80"),
            thd_i_t=Decimal("3.35"),
            thd_v_promedio_porcentaje=Decimal("1.85"),
            thd_i_total_porcentaje=Decimal("3.42"),
        ),
        energia=None,
        estado=None,
    )

    mock_use_case = MagicMock()
    mock_use_case.obtener_ultima_telemetria.return_value = mock_dto

    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "user-test", "rol": "operador"}
    app.dependency_overrides[get_telemetria_use_case] = lambda: mock_use_case

    client = TestClient(app)
    response = client.get("/api/telemetria/latest/dev-test-1")

    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    data = response.json()
    assert data["device_id"] == "dev-test-1"
    assert data["instantanea"]["thd_v_r"] == 1.85
    assert data["instantanea"]["thd_i_total_porcentaje"] == 3.42


def test_get_instantaneous_history_end_to_end():
    app = create_app()

    ahora = datetime.now(timezone.utc)
    mock_item = LecturaInstantaneaDTO(
        recorded_at=ahora,
        voltage_r=Decimal("220.0"),
        voltage_s=Decimal("220.0"),
        voltage_t=Decimal("220.0"),
        current_r=Decimal("5.0"),
        current_s=Decimal("5.0"),
        current_t=Decimal("5.0"),
        total_active_power=Decimal("3300.0"),
        thd_v_r=Decimal("1.50"),
        thd_i_r=Decimal("2.80"),
    )

    mock_use_case = MagicMock()
    mock_use_case.listar_instantaneas.return_value = [mock_item]

    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "user-test", "rol": "operador"}
    app.dependency_overrides[get_telemetria_use_case] = lambda: mock_use_case

    client = TestClient(app)
    response = client.get("/api/telemetria/instantaneous/dev-test-1?limit=10&hours=24")

    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    data = response.json()
    assert len(data) == 1
    assert data[0]["thd_v_r"] == 1.50
