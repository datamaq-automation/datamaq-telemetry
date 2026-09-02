"""Pruebas de integración de la agregación de energía por periodo (granularity=day|month)."""

from datetime import date
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.telemetria_dto import EnergiaAgregadaDTO
from src.infrastructure.fastapi.dependencies import (
    get_telemetria_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.server import create_app


def test_get_energy_aggregated_day_end_to_end():
    app = create_app()

    mock_use_case = MagicMock()
    mock_use_case.listar_energia_agregada.return_value = [
        EnergiaAgregadaDTO(periodo=date(2026, 9, 1), energia_activa_neta_kwh=None),
        EnergiaAgregadaDTO(periodo=date(2026, 9, 2), energia_activa_neta_kwh=5.0),
    ]

    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "user-test", "rol": "operador"}
    app.dependency_overrides[get_telemetria_use_case] = lambda: mock_use_case

    client = TestClient(app)
    response = client.get(
        "/api/telemetria/energy/725dfb4c-2610-4405-878a-d718b4f428a4"
        "?granularity=day&timezone=America/Argentina/Buenos_Aires"
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["periodo"] == "2026-09-01"
    assert data[0]["energia_activa_neta_kwh"] is None
    assert data[1]["periodo"] == "2026-09-02"
    assert data[1]["energia_activa_neta_kwh"] == 5.0
    mock_use_case.listar_energia_agregada.assert_called_once()


def test_get_energy_granularity_invalida_422():
    app = create_app()

    mock_use_case = MagicMock()

    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "user-test", "rol": "operador"}
    app.dependency_overrides[get_telemetria_use_case] = lambda: mock_use_case

    client = TestClient(app)
    response = client.get("/api/telemetria/energy/725dfb4c-2610-4405-878a-d718b4f428a4?granularity=week")

    assert response.status_code == 422
    mock_use_case.listar_energia_agregada.assert_not_called()
