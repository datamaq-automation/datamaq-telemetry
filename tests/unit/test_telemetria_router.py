"""tests/unit/test_telemetria_router.py — Tests unitarios completos para telemetria_router."""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.application.dtos.alerta_dto import AlertaResponseDTO
from src.application.dtos.telemetria_dto import (
    AcumuladoEnergiaDTO,
    AnaliticaCalidadEnergiaDTO,
    DiagnosticoFaseDTO,
    DiagnosticoFasesDispositivoDTO,
    EnergiaAgregadaDTO,
    HistoricoInstantaneasDTO,
    LecturaInstantaneaDTO,
    MedicionFaseDTO,
    TelemetriaLatestResponseDTO,
)
from src.domain.telemetria.exceptions import DispositivoNoEncontradoError
from src.domain.telemetria.value_objects import EstadoFactorPotencia, EstadoTension
from src.infrastructure.fastapi.dependencies import (
    get_alertas_use_case,
    get_exportar_telemetria_use_case,
    get_telemetria_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.device_ownership import verificar_propiedad_dispositivo
from src.infrastructure.fastapi.server import create_app

AHORA = datetime(2026, 9, 12, 10, 0, 0, tzinfo=timezone.utc)
DEV_ID = "d48c49f0-3564-4000-8000-000000000001"


def _medicion_fase_dto(**kwargs) -> MedicionFaseDTO:
    base = dict(
        voltage_V=220.0,
        current_A=10.0,
        net_active_power_W=2200.0,
        net_reactive_power_VAR=100.0,
        net_apparent_power_VA=2202.27,
        power_factor=0.99,
        thd_v_pct=1.5,
        thd_i_pct=2.0,
    )
    base.update(kwargs)
    return MedicionFaseDTO(**base)


def _lectura_instantanea_dto(**kwargs) -> LecturaInstantaneaDTO:
    base = dict(
        id=1,
        dispositivo_id=DEV_ID,
        registrado_en=AHORA,
        fase_r=_medicion_fase_dto(),
        fase_s=_medicion_fase_dto(),
        fase_t=_medicion_fase_dto(),
        potencia_activa_total_W=6600.0,
        potencia_reactiva_total_VAR=300.0,
        potencia_aparente_total_VA=6606.81,
        factor_potencia_total=0.99,
        desbalance_tension_porcentaje=0.5,
        corriente_neutro_estimada_A=0.2,
        voltage_linea_V=380.0,
        tension_neutro_estimada_V=1.0,
        thd_v_promedio_pct=1.5,
        thd_i_total_pct=2.0,
        analitica=AnaliticaCalidadEnergiaDTO(
            requiere_compensacion=False,
            estado_fp=EstadoFactorPotencia.OPTIMO,
            estado_tension=EstadoTension.NORMAL,
        ),
    )
    base.update(kwargs)
    return LecturaInstantaneaDTO(**base)


def _acumulado_energia_dto(**kwargs) -> AcumuladoEnergiaDTO:
    base = dict(
        id=1,
        dispositivo_id=DEV_ID,
        registrado_en=AHORA,
        net_active_energy_kwh=1500.5,
        net_reactive_energy_kvarh=120.3,
        imported_active_energy_kwh=1500.5,
        exported_active_energy_kwh=0.0,
        imported_reactive_energy_kvarh=120.3,
        exported_reactive_energy_kvarh=0.0,
    )
    base.update(kwargs)
    return AcumuladoEnergiaDTO(**base)


def _diagnostico_fases_dto(**kwargs) -> DiagnosticoFasesDispositivoDTO:
    fase = DiagnosticoFaseDTO(
        fp_original=0.95,
        angulo_phi_grados=18.2,
        potencia_activa_w=2200.0,
        potencia_reactiva_var=100.0,
        rotacion_optima_sugerida="CORRECTA",
        fp_con_rotacion_optima=0.95,
        potencia_activa_con_rotacion_optima_w=2200.0,
        potencia_reactiva_con_rotacion_optima_var=100.0,
    )
    base = dict(
        dispositivo_id=DEV_ID,
        evaluado_en=AHORA,
        fase_r=fase,
        fase_s=fase,
        fase_t=fase,
        diagnostico_general="Instalación fasorial correcta",
        recomendacion_hardware="No se requiere reconfiguración física",
    )
    base.update(kwargs)
    return DiagnosticoFasesDispositivoDTO(**base)


def _alerta_response_dto(**kwargs) -> AlertaResponseDTO:
    base = dict(
        id=10,
        dispositivo_id=DEV_ID,
        tipo_alerta="SOBRETENSION",
        severidad="CRITICAL",
        mensaje="Tensión elevada en Fase R: 250V",
        esta_resuelta=False,
        disparada_en=AHORA,
        resuelta_en=None,
        fase="R",
        valor_medido=250.0,
        valor_umbral=242.0,
        unidad="V",
        categoria="CALIDAD_ENERGIA",
        duracion_segundos=120.0,
        observaciones=None,
    )
    base.update(kwargs)
    return AlertaResponseDTO(**base)


def _cliente(usuario: dict | None = None) -> tuple[TestClient, dict[str, MagicMock]]:
    app = create_app()
    mocks = {
        "telemetria": MagicMock(),
        "alertas": MagicMock(),
        "exportar": MagicMock(),
    }
    mocks["telemetria"].datos_desde.return_value = DATOS_DESDE
    app.dependency_overrides[get_telemetria_use_case] = lambda: mocks["telemetria"]
    app.dependency_overrides[get_alertas_use_case] = lambda: mocks["alertas"]
    app.dependency_overrides[get_exportar_telemetria_use_case] = lambda: mocks["exportar"]
    app.dependency_overrides[get_usuario_actual] = lambda: (
        usuario if usuario is not None else {"sub": "u1", "rol": "admin", "org": "org-1"}
    )
    app.dependency_overrides[verificar_propiedad_dispositivo] = lambda: None
    return TestClient(app), mocks


# ==============================================================================
# Endpoint: GET /api/v1/telemetria/latest/{device_id}
# ==============================================================================


def test_get_latest_telemetry_success():
    client, mocks = _cliente()
    mock_dto = TelemetriaLatestResponseDTO(
        device_id=DEV_ID,
        instantanea=_lectura_instantanea_dto(),
        energia=_acumulado_energia_dto(),
        analitica=AnaliticaCalidadEnergiaDTO(
            requiere_compensacion=False,
            estado_fp=EstadoFactorPotencia.OPTIMO,
            estado_tension=EstadoTension.NORMAL,
        ),
    )
    mocks["telemetria"].obtener_ultima_telemetria.return_value = mock_dto

    response = client.get(f"/api/v1/telemetria/latest/{DEV_ID}")
    assert response.status_code == 200
    data = response.json()
    assert data["device_id"] == DEV_ID
    assert data["instantanea"]["potencia_activa_total_W"] == 6600.0
    assert data["energia"]["net_active_energy_kwh"] == 1500.5
    assert data["analitica"]["estado_fp"] == "OPTIMO"
    mocks["telemetria"].obtener_ultima_telemetria.assert_called_once_with(DEV_ID)


def test_get_latest_telemetry_not_found_returns_404():
    client, mocks = _cliente()
    mocks["telemetria"].obtener_ultima_telemetria.side_effect = DispositivoNoEncontradoError(
        f"Dispositivo {DEV_ID} no encontrado"
    )

    response = client.get(f"/api/v1/telemetria/latest/{DEV_ID}")
    assert response.status_code == 404
    assert response.json()["detail"] == f"Dispositivo {DEV_ID} no encontrado"


def test_get_latest_telemetry_unexpected_error_returns_500():
    client, mocks = _cliente()
    mocks["telemetria"].obtener_ultima_telemetria.side_effect = RuntimeError("Fallo inesperado")

    response = client.get(f"/api/v1/telemetria/latest/{DEV_ID}")
    assert response.status_code == 500


# ==============================================================================
# Endpoint: GET /api/v1/telemetria/fases-diagnostico/{device_id}
# ==============================================================================


def test_get_phase_diagnostic_success():
    client, mocks = _cliente()
    mocks["telemetria"].diagnosticar_fases.return_value = _diagnostico_fases_dto()

    response = client.get(f"/api/v1/telemetria/fases-diagnostico/{DEV_ID}")
    assert response.status_code == 200
    data = response.json()
    assert data["dispositivo_id"] == DEV_ID
    assert data["diagnostico_general"] == "Instalación fasorial correcta"
    assert data["recomendacion_hardware"] == "No se requiere reconfiguración física"
    assert data["fase_r"]["rotacion_optima_sugerida"] == "CORRECTA"
    mocks["telemetria"].diagnosticar_fases.assert_called_once_with(DEV_ID)


def test_get_phase_diagnostic_not_found_returns_404():
    client, mocks = _cliente()
    mocks["telemetria"].diagnosticar_fases.side_effect = DispositivoNoEncontradoError(
        f"Dispositivo {DEV_ID} no encontrado"
    )

    response = client.get(f"/api/v1/telemetria/fases-diagnostico/{DEV_ID}")
    assert response.status_code == 404
    assert response.json()["detail"] == f"Dispositivo {DEV_ID} no encontrado"


def test_get_phase_diagnostic_unexpected_error_returns_500():
    client, mocks = _cliente()
    mocks["telemetria"].diagnosticar_fases.side_effect = ValueError("Error de cálculo fasorial")

    response = client.get(f"/api/v1/telemetria/fases-diagnostico/{DEV_ID}")
    assert response.status_code == 500


# ==============================================================================
# Endpoint: GET /api/v1/telemetria/instantaneous/{device_id}
# ==============================================================================


DATOS_DESDE = datetime(2026, 8, 29, 10, 0, 0, tzinfo=timezone.utc)


def _historico(*lecturas: LecturaInstantaneaDTO) -> HistoricoInstantaneasDTO:
    return HistoricoInstantaneasDTO(lecturas=list(lecturas), datos_desde=DATOS_DESDE)


def test_get_instantaneous_history_default_params():
    client, mocks = _cliente()
    mocks["telemetria"].historico_instantaneas.return_value = _historico(_lectura_instantanea_dto())

    response = client.get(f"/api/v1/telemetria/instantaneous/{DEV_ID}")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["dispositivo_id"] == DEV_ID
    assert response.headers["X-Datos-Desde"] == "2026-08-29T10:00:00Z"
    mocks["telemetria"].historico_instantaneas.assert_called_once_with(
        id_o_uid=DEV_ID,
        limite=500,
        desde=None,
        granularidad="auto",
        horas=None,
        hasta=None,
    )


def test_get_instantaneous_history_custom_params():
    client, mocks = _cliente()
    mocks["telemetria"].historico_instantaneas.return_value = _historico(_lectura_instantanea_dto())

    antes = datetime.now(timezone.utc) - timedelta(hours=12)
    response = client.get(f"/api/v1/telemetria/instantaneous/{DEV_ID}?limit=250&hours=12&granularity=15m")
    despues = datetime.now(timezone.utc) - timedelta(hours=12)

    assert response.status_code == 200
    mocks["telemetria"].historico_instantaneas.assert_called_once()
    _, kwargs = mocks["telemetria"].historico_instantaneas.call_args
    assert kwargs["id_o_uid"] == DEV_ID
    assert kwargs["limite"] == 250
    assert kwargs["granularidad"] == "15m"
    assert kwargs["horas"] == 12
    assert kwargs["hasta"] is None
    assert antes <= kwargs["desde"] <= despues


def test_get_instantaneous_history_con_hasta_desplaza_la_ventana():
    client, mocks = _cliente()
    mocks["telemetria"].historico_instantaneas.return_value = _historico()

    response = client.get(f"/api/v1/telemetria/instantaneous/{DEV_ID}?hours=8&hasta=2026-09-10T08:00:00Z")

    assert response.status_code == 200
    assert response.json() == []
    assert response.headers["X-Datos-Desde"] == "2026-08-29T10:00:00Z"
    _, kwargs = mocks["telemetria"].historico_instantaneas.call_args
    assert kwargs["hasta"] == datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc)
    assert kwargs["desde"] == datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc)
    assert kwargs["horas"] == 8


def test_get_instantaneous_history_hasta_invalido_es_422():
    client, _ = _cliente()
    assert client.get(f"/api/v1/telemetria/instantaneous/{DEV_ID}?hasta=ayer").status_code == 422


def test_get_instantaneous_history_validation_errors():
    client, _ = _cliente()

    # limit fuera de rango (ge=1, le=5000)
    assert client.get(f"/api/v1/telemetria/instantaneous/{DEV_ID}?limit=0").status_code == 422
    assert client.get(f"/api/v1/telemetria/instantaneous/{DEV_ID}?limit=5001").status_code == 422

    # hours fuera de rango (ge=1, le=720)
    assert client.get(f"/api/v1/telemetria/instantaneous/{DEV_ID}?hours=0").status_code == 422
    assert client.get(f"/api/v1/telemetria/instantaneous/{DEV_ID}?hours=721").status_code == 422


def test_get_instantaneous_history_not_found_returns_404():
    client, mocks = _cliente()
    mocks["telemetria"].historico_instantaneas.side_effect = DispositivoNoEncontradoError("Dispositivo inexistente")

    response = client.get(f"/api/v1/telemetria/instantaneous/{DEV_ID}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Dispositivo inexistente"


def test_get_instantaneous_history_unexpected_error_returns_500():
    client, mocks = _cliente()
    mocks["telemetria"].historico_instantaneas.side_effect = RuntimeError("Error inesperado en BD")

    response = client.get(f"/api/v1/telemetria/instantaneous/{DEV_ID}")
    assert response.status_code == 500


# ==============================================================================
# Endpoint: GET /api/v1/telemetria/energy/{device_id}
# ==============================================================================


def test_get_energy_history_raw_without_days():
    client, mocks = _cliente()
    mocks["telemetria"].listar_energias.return_value = [_acumulado_energia_dto()]

    response = client.get(f"/api/v1/telemetria/energy/{DEV_ID}?granularity=raw&limit=50")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["imported_active_energy_kwh"] == 1500.5
    mocks["telemetria"].listar_energias.assert_called_once_with(DEV_ID, 50, None)
    assert response.headers["X-Datos-Desde"] == "2026-08-29T10:00:00Z"


def test_get_energy_history_raw_with_days():
    client, mocks = _cliente()
    mocks["telemetria"].listar_energias.return_value = [_acumulado_energia_dto()]

    antes = datetime.now(timezone.utc) - timedelta(days=7)
    response = client.get(f"/api/v1/telemetria/energy/{DEV_ID}?granularity=raw&days=7&limit=100")
    despues = datetime.now(timezone.utc) - timedelta(days=7)

    assert response.status_code == 200
    mocks["telemetria"].listar_energias.assert_called_once()
    args, _ = mocks["telemetria"].listar_energias.call_args
    assert args[0] == DEV_ID
    assert args[1] == 100
    assert antes <= args[2] <= despues


def test_get_energy_history_aggregated_day():
    client, mocks = _cliente()
    mocks["telemetria"].listar_energia_agregada.return_value = [
        EnergiaAgregadaDTO(periodo=date(2026, 9, 1), energia_activa_neta_kwh=10.5),
        EnergiaAgregadaDTO(periodo=date(2026, 9, 2), energia_activa_neta_kwh=12.0),
    ]

    response = client.get(
        f"/api/v1/telemetria/energy/{DEV_ID}?granularity=day&days=30&timezone=America/Argentina/Cordoba"
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["periodo"] == "2026-09-01"
    assert data[0]["energia_activa_neta_kwh"] == 10.5
    mocks["telemetria"].listar_energia_agregada.assert_called_once_with(DEV_ID, "day", "America/Argentina/Cordoba", 30)
    # `days=30` se acota a la retención sin aviso en el body: el header informa el período real.
    assert response.headers["X-Datos-Desde"] == "2026-08-29T10:00:00Z"
    mocks["telemetria"].datos_desde.assert_called_once_with(DEV_ID)


def test_get_energy_history_aggregated_month():
    client, mocks = _cliente()
    mocks["telemetria"].listar_energia_agregada.return_value = [
        EnergiaAgregadaDTO(periodo=date(2026, 8, 1), energia_activa_neta_kwh=320.0),
        EnergiaAgregadaDTO(periodo=date(2026, 9, 1), energia_activa_neta_kwh=415.5),
    ]

    response = client.get(f"/api/v1/telemetria/energy/{DEV_ID}?granularity=month&days=60")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["periodo"] == "2026-08-01"
    assert data[1]["energia_activa_neta_kwh"] == 415.5
    mocks["telemetria"].listar_energia_agregada.assert_called_once_with(
        DEV_ID, "month", "America/Argentina/Buenos_Aires", 60
    )


def test_get_energy_history_validation_errors():
    client, _ = _cliente()

    # Granularidad no válida
    assert client.get(f"/api/v1/telemetria/energy/{DEV_ID}?granularity=year").status_code == 422
    assert client.get(f"/api/v1/telemetria/energy/{DEV_ID}?granularity=1h").status_code == 422

    # Límite superior a 1000
    assert client.get(f"/api/v1/telemetria/energy/{DEV_ID}?limit=1001").status_code == 422


def test_get_energy_history_not_found_returns_404():
    client, mocks = _cliente()
    mocks["telemetria"].listar_energias.side_effect = DispositivoNoEncontradoError(
        f"Dispositivo {DEV_ID} no encontrado"
    )

    response = client.get(f"/api/v1/telemetria/energy/{DEV_ID}?granularity=raw")
    assert response.status_code == 404
    assert response.json()["detail"] == f"Dispositivo {DEV_ID} no encontrado"


def test_get_energy_history_unexpected_error_returns_500():
    client, mocks = _cliente()
    mocks["telemetria"].listar_energia_agregada.side_effect = RuntimeError("Error en agregación")

    response = client.get(f"/api/v1/telemetria/energy/{DEV_ID}?granularity=day")
    assert response.status_code == 500


# ==============================================================================
# Endpoint: GET /api/v1/telemetria/alerts/{device_id}
# ==============================================================================


def test_get_alerts_history_defaults():
    client, mocks = _cliente()
    mocks["alertas"].listar_alertas.return_value = [_alerta_response_dto()]

    response = client.get(f"/api/v1/telemetria/alerts/{DEV_ID}")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["tipo_alerta"] == "SOBRETENSION"
    assert data[0]["severidad"] == "CRITICAL"
    mocks["alertas"].listar_alertas.assert_called_once_with(
        dispositivo_id=DEV_ID,
        solo_abiertas=False,
        severidad=None,
        limite=100,
        desde=None,
        hasta=None,
    )


def test_get_alerts_history_custom_filters():
    client, mocks = _cliente()
    mocks["alertas"].listar_alertas.return_value = [
        _alerta_response_dto(severidad="WARNING", tipo_alerta="DESBALANCE_TENSION")
    ]

    response = client.get(
        f"/api/v1/telemetria/alerts/{DEV_ID}"
        "?solo_abiertas=true&severidad=WARNING&limit=50"
        "&desde=2026-09-01T00:00:00Z&hasta=2026-09-10T23:59:59Z"
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["severidad"] == "WARNING"
    mocks["alertas"].listar_alertas.assert_called_once_with(
        dispositivo_id=DEV_ID,
        solo_abiertas=True,
        severidad="WARNING",
        limite=50,
        desde=datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc),
        hasta=datetime(2026, 9, 10, 23, 59, 59, tzinfo=timezone.utc),
    )


def test_get_alerts_history_limit_exceeded_returns_422():
    client, _ = _cliente()
    response = client.get(f"/api/v1/telemetria/alerts/{DEV_ID}?limit=501")
    assert response.status_code == 422


def test_get_alerts_history_not_found_returns_404():
    client, mocks = _cliente()
    mocks["alertas"].listar_alertas.side_effect = DispositivoNoEncontradoError(f"Dispositivo {DEV_ID} no encontrado")

    response = client.get(f"/api/v1/telemetria/alerts/{DEV_ID}")
    assert response.status_code == 404
    assert response.json()["detail"] == f"Dispositivo {DEV_ID} no encontrado"


def test_get_alerts_history_unexpected_error_returns_500():
    client, mocks = _cliente()
    mocks["alertas"].listar_alertas.side_effect = RuntimeError("Error al consultar alertas")

    response = client.get(f"/api/v1/telemetria/alerts/{DEV_ID}")
    assert response.status_code == 500


# ==============================================================================
# Endpoint: GET /api/v1/telemetria/exportar/csv
# ==============================================================================


def test_exportar_telemetria_csv_success():
    client, mocks = _cliente()
    csv_chunks = ["registrado_en,potencia_w\n", "2026-09-12T10:00:00Z,6600.0\n"]
    mocks["exportar"].ejecutar.return_value = iter(csv_chunks)

    response = client.get(f"/api/v1/telemetria/exportar/csv?dispositivo_id={DEV_ID}&limite=5000")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert f'attachment; filename="telemetria_{DEV_ID}_' in response.headers["content-disposition"]
    assert response.headers["content-disposition"].endswith('.csv"')
    assert response.text == "".join(csv_chunks)
    mocks["exportar"].ejecutar.assert_called_once_with(
        dispositivo_id=DEV_ID,
        desde=None,
        hasta=None,
        limite=5000,
    )


def test_exportar_telemetria_csv_with_date_range():
    client, mocks = _cliente()
    mocks["exportar"].ejecutar.return_value = iter(["col1\n", "val1\n"])

    response = client.get(
        f"/api/v1/telemetria/exportar/csv?dispositivo_id={DEV_ID}&desde=2026-09-01T00:00:00Z&hasta=2026-09-05T12:00:00Z"
    )
    assert response.status_code == 200
    mocks["exportar"].ejecutar.assert_called_once_with(
        dispositivo_id=DEV_ID,
        desde=datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc),
        hasta=datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc),
        limite=10000,
    )


def test_exportar_telemetria_csv_missing_dispositivo_id_422():
    client, _ = _cliente()
    response = client.get("/api/v1/telemetria/exportar/csv")
    assert response.status_code == 422


def test_exportar_telemetria_csv_limite_validation_errors():
    client, _ = _cliente()
    # limite ge=1, le=50000
    assert client.get(f"/api/v1/telemetria/exportar/csv?dispositivo_id={DEV_ID}&limite=0").status_code == 422
    assert client.get(f"/api/v1/telemetria/exportar/csv?dispositivo_id={DEV_ID}&limite=50001").status_code == 422


def test_exportar_telemetria_csv_not_found_returns_404():
    client, mocks = _cliente()
    mocks["exportar"].ejecutar.side_effect = DispositivoNoEncontradoError(f"Dispositivo {DEV_ID} no encontrado")

    response = client.get(f"/api/v1/telemetria/exportar/csv?dispositivo_id={DEV_ID}")
    assert response.status_code == 404
    assert response.json()["detail"] == f"Dispositivo {DEV_ID} no encontrado"


def test_exportar_telemetria_csv_unexpected_error_returns_500():
    client, mocks = _cliente()
    mocks["exportar"].ejecutar.side_effect = RuntimeError("Fallo exportando CSV")

    response = client.get(f"/api/v1/telemetria/exportar/csv?dispositivo_id={DEV_ID}")
    assert response.status_code == 500


# ==============================================================================
# Security and Dependency Overrides (Auth & Device Ownership)
# ==============================================================================


def test_unauthenticated_request_rejected():
    app = create_app()

    def _raise_unauthorized():
        raise HTTPException(status_code=401, detail="Token no proporcionado")

    app.dependency_overrides[get_usuario_actual] = _raise_unauthorized
    client = TestClient(app)

    response = client.get(f"/api/v1/telemetria/latest/{DEV_ID}")
    assert response.status_code == 401
    assert response.json()["detail"] == "Token no proporcionado"


def test_device_ownership_forbidden_rejected():
    app = create_app()
    app.dependency_overrides[get_usuario_actual] = lambda: {
        "sub": "u1",
        "rol": "operador",
        "org": "org-2",
    }

    def _raise_device_forbidden():
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")

    app.dependency_overrides[verificar_propiedad_dispositivo] = _raise_device_forbidden
    client = TestClient(app)

    response = client.get(f"/api/v1/telemetria/latest/{DEV_ID}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Dispositivo no encontrado"
