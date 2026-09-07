from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.mappers.csv_streaming_mapper import BOM_UTF8
from src.infrastructure.fastapi.dependencies import (
    get_exportar_cargas_use_case,
    get_exportar_disponibilidad_use_case,
    get_exportar_telemetria_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.server import create_app


def test_exportar_telemetria_csv_streaming_end_to_end():
    app = create_app()

    ahora = datetime(2026, 9, 7, 10, 0, 0, tzinfo=timezone.utc)
    mock_use_case = MagicMock()
    mock_use_case.ejecutar.return_value = iter(
        [
            BOM_UTF8,
            "timestamp_utc,potencia_activa_total_w,potencia_l1_w,potencia_l2_w,potencia_l3_w,tension_l1_v,tension_l2_v,tension_l3_v,corriente_l1_a,corriente_l2_a,corriente_l3_a,factor_potencia,desbalance_tension_pct\r\n",
            f"{ahora.isoformat()},6600.00,2200.00,2200.00,2200.00,2200.00,2200.00,2200.00,10.00,10.00,10.00,0.98,0.50\r\n",
        ]
    )

    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "user-test", "rol": "operador"}
    app.dependency_overrides[get_exportar_telemetria_use_case] = lambda: mock_use_case

    client = TestClient(app)
    response = client.get("/api/v1/telemetria/exportar/csv?dispositivo_id=dev-test-1")

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert 'attachment; filename="telemetria_dev-test-1_' in response.headers["content-disposition"]
    assert response.text.startswith(BOM_UTF8)
    assert "timestamp_utc,potencia_activa_total_w" in response.text
    assert "6600.00,2200.00" in response.text


def test_exportar_disponibilidad_csv_streaming_end_to_end():
    app = create_app()

    mock_use_case = MagicMock()
    mock_use_case.ejecutar.return_value = iter(
        [
            BOM_UTF8,
            "# Resumen OEE: 90.0% | MTBF: 24.0h | MTTR: 1.0h\r\n",
            "evento_id,maquina_id,estado,tipo_parada,inicio_utc,fin_utc,duracion_segundos,duracion_minutos,potencia_promedio_w,origen_clasificacion,comentario\r\n",
            "1,maq-test-1,PARADA,PROGRAMADA,2026-09-07T08:00:00+00:00,2026-09-07T08:30:00+00:00,1800.00,30.00,0.00,REGLA,Mantenimiento preventivo\r\n",
        ]
    )

    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "user-test", "rol": "operador"}
    app.dependency_overrides[get_exportar_disponibilidad_use_case] = lambda: mock_use_case

    client = TestClient(app)
    response = client.get("/api/v1/disponibilidad/maquinas/maq-test-1/exportar/csv?dias=7")

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert 'attachment; filename="disponibilidad_maq-test-1_' in response.headers["content-disposition"]
    assert response.text.startswith(BOM_UTF8)
    assert "# Resumen OEE: 90.0%" in response.text
    assert "maq-test-1,PARADA,PROGRAMADA" in response.text


def test_exportar_cargas_csv_streaming_end_to_end():
    app = create_app()

    mock_use_case = MagicMock()
    mock_use_case.ejecutar.return_value = iter(
        [
            BOM_UTF8,
            "intervalo_id,dispositivo_id,carga_nombre,categoria,inicio_utc,fin_utc,duracion_minutos,potencia_media_w,energia_estimada_kwh,confianza_pct,estado_atribucion\r\n",
            "10,dev-test-1,Compresor 1,FUERZA_MOTRIZ,2026-09-07T08:00:00+00:00,2026-09-07T08:20:00+00:00,20.00,5000.00,1.6667,95.0,ATRIBUIDO\r\n",
        ]
    )

    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "user-test", "rol": "operador"}
    app.dependency_overrides[get_exportar_cargas_use_case] = lambda: mock_use_case

    client = TestClient(app)
    response = client.get("/api/v1/cargas/exportar/csv?dispositivo_id=dev-test-1")

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert 'attachment; filename="cargas_dev-test-1_' in response.headers["content-disposition"]
    assert response.text.startswith(BOM_UTF8)
    assert "intervalo_id,dispositivo_id,carga_nombre" in response.text
    assert "Compresor 1,FUERZA_MOTRIZ" in response.text
    assert "ATRIBUIDO" in response.text
