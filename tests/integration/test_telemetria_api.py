"""tests/integration/test_telemetria_api.py — Pruebas de integración de la API de telemetría: registro de rutas, ejecución end-to-end y serialización DTO."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.telemetria_dto import (
    HistoricoInstantaneasDTO,
    LecturaInstantaneaDTO,
    MedicionFaseDTO,
    TelemetriaLatestResponseDTO,
)
from src.infrastructure.fastapi.dependencies import (
    get_telemetria_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.device_ownership import verificar_propiedad_dispositivo
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
    return {k: v for k, v in rutas.items() if k.startswith("/api/v1/telemetria")}


def test_create_app_registra_rutas_telemetria():
    app = create_app()
    rutas = _rutas_telemetria(app)

    assert "/api/v1/telemetria/latest/{device_id}" in rutas
    assert "GET" in rutas["/api/v1/telemetria/latest/{device_id}"]

    assert "/api/v1/telemetria/instantaneous/{device_id}" in rutas
    assert "GET" in rutas["/api/v1/telemetria/instantaneous/{device_id}"]

    assert "/api/v1/telemetria/energy/{device_id}" in rutas
    assert "GET" in rutas["/api/v1/telemetria/energy/{device_id}"]

    assert "/api/v1/telemetria/alerts/{device_id}" in rutas
    assert "GET" in rutas["/api/v1/telemetria/alerts/{device_id}"]


def test_get_latest_telemetry_end_to_end_con_thd():
    app = create_app()

    ahora = datetime.now(timezone.utc)
    mock_dto = TelemetriaLatestResponseDTO(
        device_id="dev-test-1",
        instantanea=LecturaInstantaneaDTO(
            dispositivo_id="dev-test-1",
            registrado_en=ahora,
            fase_r=MedicionFaseDTO(
                voltage_V=220.5,
                current_A=10.2,
                net_active_power_W=2249.1,
                thd_v_pct=1.85,
                thd_i_pct=3.42,
            ),
            fase_s=MedicionFaseDTO(
                voltage_V=221.0,
                current_A=9.8,
                net_active_power_W=2165.8,
                thd_v_pct=1.90,
                thd_i_pct=3.50,
            ),
            fase_t=MedicionFaseDTO(
                voltage_V=219.8,
                current_A=10.5,
                net_active_power_W=2307.9,
                thd_v_pct=1.80,
                thd_i_pct=3.35,
            ),
            potencia_activa_total_W=6722.8,
            thd_v_promedio_pct=1.85,
            thd_i_total_pct=3.42,
            nivel_tension="BT",
            tension_nominal_V=380.0,
            tension_nominal_fase_V=219.4,
        ),
        energia=None,
    )

    mock_use_case = MagicMock()
    mock_use_case.obtener_ultima_telemetria.return_value = mock_dto

    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "user-test", "rol": "operador"}
    app.dependency_overrides[verificar_propiedad_dispositivo] = lambda: None
    app.dependency_overrides[get_telemetria_use_case] = lambda: mock_use_case

    client = TestClient(app)
    response = client.get("/api/v1/telemetria/latest/dev-test-1")

    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    data = response.json()
    assert data["device_id"] == "dev-test-1"
    assert data["instantanea"]["thd_v_promedio_pct"] == 1.85
    assert data["instantanea"]["thd_i_total_pct"] == 3.42
    assert data["instantanea"]["nivel_tension"] == "BT"
    assert data["instantanea"]["tension_nominal_V"] == 380.0
    assert data["instantanea"]["tension_nominal_fase_V"] == 219.4


def test_get_instantaneous_history_end_to_end():
    app = create_app()

    ahora = datetime.now(timezone.utc)
    mock_item = LecturaInstantaneaDTO(
        dispositivo_id="dev-test-1",
        registrado_en=ahora,
        fase_r=MedicionFaseDTO(voltage_V=220.0, current_A=5.0, thd_v_pct=1.50, thd_i_pct=2.80),
        fase_s=MedicionFaseDTO(voltage_V=220.0, current_A=5.0, thd_v_pct=1.50, thd_i_pct=2.80),
        fase_t=MedicionFaseDTO(voltage_V=220.0, current_A=5.0, thd_v_pct=1.50, thd_i_pct=2.80),
        potencia_activa_total_W=3300.0,
        thd_v_promedio_pct=1.50,
        thd_i_total_pct=2.80,
    )

    mock_use_case = MagicMock()
    mock_use_case.historico_instantaneas.return_value = HistoricoInstantaneasDTO(
        lecturas=[mock_item], datos_desde=ahora
    )

    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "user-test", "rol": "operador"}
    app.dependency_overrides[verificar_propiedad_dispositivo] = lambda: None
    app.dependency_overrides[get_telemetria_use_case] = lambda: mock_use_case

    client = TestClient(app)
    response = client.get("/api/v1/telemetria/instantaneous/dev-test-1?limit=10&hours=24")

    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    assert "X-Datos-Desde" in response.headers
    data = response.json()
    assert len(data) == 1
    assert data[0]["thd_v_promedio_pct"] == 1.50


def test_get_instantaneous_history_empty_result_returns_200_empty_list():
    app = create_app()

    mock_use_case = MagicMock()
    mock_use_case.historico_instantaneas.return_value = HistoricoInstantaneasDTO(
        lecturas=[], datos_desde=datetime(2026, 9, 1, tzinfo=timezone.utc)
    )

    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "user-test", "rol": "invitado"}
    app.dependency_overrides[verificar_propiedad_dispositivo] = lambda: None
    app.dependency_overrides[get_telemetria_use_case] = lambda: mock_use_case

    client = TestClient(app)
    response = client.get("/api/v1/telemetria/instantaneous/725dfb4c-2610-4405-878a-d718b4f428a4?limit=100&hours=24")

    assert response.status_code == 200
    assert response.json() == []


def test_get_energy_history_end_to_end():
    from src.application.dtos.telemetria_dto import AcumuladoEnergiaDTO

    app = create_app()

    ahora = datetime.now(timezone.utc)
    mock_energy = AcumuladoEnergiaDTO(
        dispositivo_id="725dfb4c-2610-4405-878a-d718b4f428a4",
        registrado_en=ahora,
        imported_active_energy_kwh=1250.45,
        exported_active_energy_kwh=0.0,
        imported_reactive_energy_kvarh=120.30,
        exported_reactive_energy_kvarh=0.0,
    )

    mock_use_case = MagicMock()
    mock_use_case.listar_energias.return_value = [mock_energy]

    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "user-test", "rol": "invitado"}
    app.dependency_overrides[verificar_propiedad_dispositivo] = lambda: None
    app.dependency_overrides[get_telemetria_use_case] = lambda: mock_use_case

    client = TestClient(app)
    response = client.get("/api/v1/telemetria/energy/725dfb4c-2610-4405-878a-d718b4f428a4?limit=100&days=7")

    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    data = response.json()
    assert len(data) == 1
    assert data[0]["imported_active_energy_kwh"] == 1250.45


def test_get_latest_telemetry_end_to_end_con_analitica_calidad_energia():
    from src.application.dtos.telemetria_dto import AnaliticaCalidadEnergiaDTO

    app = create_app()

    ahora = datetime.now(timezone.utc)
    mock_analitica = AnaliticaCalidadEnergiaDTO(
        requiere_compensacion=True,
        potencia_reactiva_a_compensar_kvar=45.83,
        banco_sugerido_kvar=50.0,
        penalizacion_estimada_ars=1310625.0,
        desbalance_tension_porcentaje=2.27,
        desbalance_corriente_porcentaje=5.50,
        estado_fp="PENALIZADO",
        estado_tension="NORMAL",
    )
    mock_dto = TelemetriaLatestResponseDTO(
        device_id="dev-test-analitica",
        instantanea=LecturaInstantaneaDTO(
            dispositivo_id="dev-test-analitica",
            registrado_en=ahora,
            fase_r=MedicionFaseDTO(voltage_V=220.0, current_A=150.0, net_active_power_W=33333.3),
            fase_s=MedicionFaseDTO(voltage_V=215.0, current_A=155.0, net_active_power_W=33333.3),
            fase_t=MedicionFaseDTO(voltage_V=225.0, current_A=145.0, net_active_power_W=33333.4),
            potencia_activa_total_W=100000.0,
            factor_potencia_total=0.80,
            desbalance_tension_porcentaje=2.27,
            analitica=mock_analitica,
        ),
        energia=None,
        analitica=mock_analitica,
    )

    mock_use_case = MagicMock()
    mock_use_case.obtener_ultima_telemetria.return_value = mock_dto

    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "user-test", "rol": "operador"}
    app.dependency_overrides[verificar_propiedad_dispositivo] = lambda: None
    app.dependency_overrides[get_telemetria_use_case] = lambda: mock_use_case

    client = TestClient(app)
    response = client.get("/api/v1/telemetria/latest/dev-test-analitica")

    assert response.status_code == 200
    data = response.json()
    assert data["device_id"] == "dev-test-analitica"
    assert "analitica" in data
    assert data["analitica"]["requiere_compensacion"] is True
    assert data["analitica"]["potencia_reactiva_a_compensar_kvar"] == 45.83
    assert data["analitica"]["banco_sugerido_kvar"] == 50.0
    assert data["analitica"]["penalizacion_estimada_ars"] == 1310625.0
    assert data["analitica"]["desbalance_tension_porcentaje"] == 2.27
    assert data["analitica"]["desbalance_corriente_porcentaje"] == 5.50
    assert data["analitica"]["estado_fp"] == "PENALIZADO"
    assert data["analitica"]["estado_tension"] == "NORMAL"

    # Also in instantanea.analitica
    assert data["instantanea"]["analitica"]["requiere_compensacion"] is True
