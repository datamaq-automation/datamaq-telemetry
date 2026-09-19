"""tests/unit/test_produccion_router.py — Tests de integración HTTP para sensórica de proceso y SEC."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.adapters.gateways.in_memory_variables_proceso_repository import (
    InMemoryVariablesProcesoRepository,
)
from src.application.use_cases.calcular_sec_hibrido import CalcularSecHibridoUseCase
from src.application.use_cases.registrar_lectura_proceso import RegistrarLecturaProcesoUseCase
from src.domain.produccion.entities import ConfiguracionMedicionMaquina
from src.infrastructure.auth.jwt_token_service import JwtTokenService
from src.infrastructure.fastapi.dependencies import get_usuarios_repository
from src.infrastructure.fastapi.routes.produccion_router import (
    get_calcular_sec_use_case,
    get_registrar_lectura_use_case,
    get_variables_proceso_repository,
)
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.settings.config import get_settings


@pytest.fixture
def repo_proceso() -> InMemoryVariablesProcesoRepository:
    repo = InMemoryVariablesProcesoRepository()
    # Guardar una configuración de máquina dedicada
    repo.guardar_configuracion(
        ConfiguracionMedicionMaquina(
            maquina_id="prensa-01",
            nombre="Prensa Hidráulica 1",
            potencia_nominal_kw=22.0,
            nodo_alimentacion="CCM-PRENSAS",
            dispositivo_medidor_id="esp32-prensa-01",
        )
    )
    return repo


@pytest.fixture
def client_proceso(repo_proceso):
    app = create_app()
    mock_repo_usuarios = MagicMock()
    mock_repo_usuarios.obtener_por_id.return_value = None
    app.dependency_overrides[get_usuarios_repository] = lambda: mock_repo_usuarios

    app.dependency_overrides[get_variables_proceso_repository] = lambda: repo_proceso
    app.dependency_overrides[get_registrar_lectura_use_case] = lambda: RegistrarLecturaProcesoUseCase(repo_proceso)
    app.dependency_overrides[get_calcular_sec_use_case] = lambda: CalcularSecHibridoUseCase(repo_proceso)

    return TestClient(app)


def _crear_token(rol: str = "operador") -> str:
    settings = get_settings()
    token_service = JwtTokenService(settings.API_SECRET_KEY)
    expira = datetime.now(timezone.utc) + timedelta(hours=1)
    return token_service.generar(
        usuario_id="usr-123",
        usuario="operador_test",
        expira_en=expira,
        rol=rol,
    )


def test_registrar_lectura_sin_auth_retorna_401(client_proceso):
    res = client_proceso.post(
        "/api/v1/produccion/lecturas",
        json={
            "maquinaId": "prensa-01",
            "momento": datetime.now(timezone.utc).isoformat(),
            "variableTipo": "CONTEO_CORTES",
            "deltaValor": 1.0,
            "valorAcumulado": 50.0,
        },
    )
    assert res.status_code == 401


def test_registrar_lectura_con_auth_retorna_201(client_proceso):
    token = _crear_token()
    client_proceso.cookies.set("datamaq_token", token)

    ahora = datetime.now(timezone.utc).isoformat()
    res = client_proceso.post(
        "/api/v1/produccion/lecturas",
        json={
            "maquinaId": "prensa-01",
            "momento": ahora,
            "variableTipo": "LONGITUD_METROS",
            "deltaValor": 12.5,
            "valorAcumulado": 150.0,
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["maquinaId"] == "prensa-01"
    assert data["variableTipo"] == "LONGITUD_METROS"
    assert data["deltaValor"] == 12.5


def test_calcular_sec_maquina_dedicada(client_proceso):
    token = _crear_token()
    client_proceso.cookies.set("datamaq_token", token)

    t0 = datetime(2026, 9, 19, 8, 0, tzinfo=timezone.utc).isoformat()
    t1 = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc).isoformat()

    res = client_proceso.post(
        "/api/v1/produccion/enpi/calcular-sec",
        json={
            "maquinaId": "prensa-01",
            "periodoInicio": t0,
            "periodoFin": t1,
            "energiaKwh": 60.0,
            "unidadesProduccion": 300.0,
            "horasActivasProceso": 3.0,
            "potenciaMediaKw": 18.0,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["modoMedicion"] == "DEDICADA_SECCIONAL"
    assert data["secKwhPorUnidad"] == 0.2
    assert data["energiaProductivaKwh"] == 54.0
    assert data["energiaNoProductivaKwh"] == 6.0


def test_calcular_sec_maquina_tgbt_fallback(client_proceso):
    token = _crear_token()
    client_proceso.cookies.set("datamaq_token", token)

    t0 = datetime(2026, 9, 19, 8, 0, tzinfo=timezone.utc).isoformat()
    t1 = datetime(2026, 9, 19, 16, 0, tzinfo=timezone.utc).isoformat()

    # cortadora-desconocida no está configurada, usa fallback en TGBT
    res = client_proceso.post(
        "/api/v1/produccion/enpi/calcular-sec",
        json={
            "maquinaId": "cortadora-desconocida",
            "periodoInicio": t0,
            "periodoFin": t1,
            "energiaKwh": 200.0,
            "unidadesProduccion": 500.0,
            "horasActivasProceso": 4.0,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["modoMedicion"] == "AGREGADA_TGBT"
    assert "Desagregación asistida en TGBT" in data["detalleEstimacion"]
