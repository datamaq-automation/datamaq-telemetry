"""Verifica que create_app() registra el router de disponibilidad de máquina sin conexión a DB."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.disponibilidad_dto import MetricasDisponibilidadOEEResponseDTO
from src.infrastructure.fastapi.dependencies import get_disponibilidad_use_case, get_usuario_actual
from src.infrastructure.fastapi.server import create_app


def test_create_app_registra_router_disponibilidad():
    app = create_app()
    rutas: dict[str, set[str]] = {}
    for ruta in app.routes:
        if hasattr(ruta, "methods") and hasattr(ruta, "path"):
            rutas.setdefault(ruta.path, set()).update(ruta.methods or set())
        elif hasattr(ruta, "original_router"):
            for subruta in ruta.original_router.routes:
                if hasattr(subruta, "methods") and hasattr(subruta, "path"):
                    rutas.setdefault(subruta.path, set()).update(subruta.methods or set())

    assert "/api/v1/disponibilidad/maquinas" in rutas
    assert "GET" in rutas["/api/v1/disponibilidad/maquinas"]
    assert "POST" in rutas["/api/v1/disponibilidad/maquinas"]
    assert "/api/v1/disponibilidad/maquinas/{maquina_id}/histograma" in rutas
    assert "/api/v1/disponibilidad/maquinas/{maquina_id}/eventos" in rutas
    assert "/api/v1/disponibilidad/maquinas/{maquina_id}/metricas-oee" in rutas
    assert "GET" in rutas["/api/v1/disponibilidad/maquinas/{maquina_id}/metricas-oee"]
    assert "/api/v1/disponibilidad/eventos/{evento_id}/corregir" in rutas
    assert "POST" in rutas["/api/v1/disponibilidad/eventos/{evento_id}/corregir"]
    assert "/api/v1/disponibilidad/paradas-programadas" in rutas


def test_obtener_metricas_oee_endpoint():
    app = create_app()
    mock_use_case = MagicMock()
    inicio = datetime(2026, 9, 1, tzinfo=timezone.utc)
    fin = datetime(2026, 9, 7, tzinfo=timezone.utc)
    mock_use_case.calcular_metricas_oee.return_value = MetricasDisponibilidadOEEResponseDTO(
        maquina_id="maq-1",
        periodo_inicio=inicio,
        periodo_fin=fin,
        tiempo_total_segundos=3600.0,
        tiempo_marcha_segundos=3000.0,
        tiempo_parada_programada_segundos=0.0,
        tiempo_parada_no_programada_segundos=600.0,
        disponibilidad_oee_porcentaje=83.33,
        mtbf_horas=0.83,
        mttr_horas=0.17,
        cantidad_paradas_no_programadas=1,
        cantidad_paradas_programadas=0,
        cantidad_ciclos_marcha=1,
    )
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "test-user", "rol": "operador"}
    app.dependency_overrides[get_disponibilidad_use_case] = lambda: mock_use_case

    client = TestClient(app)
    response = client.get("/api/v1/disponibilidad/maquinas/maq-1/metricas-oee?dias=7")

    assert response.status_code == 200
    data = response.json()
    assert data["maquina_id"] == "maq-1"
    assert data["disponibilidad_oee_porcentaje"] == 83.33
    assert data["cantidad_paradas_no_programadas"] == 1
    mock_use_case.calcular_metricas_oee.assert_called_once()
