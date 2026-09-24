"""tests/unit/test_sge_endpoints_iso50001.py — Tests para endpoints de Balance, CUSUM y EnB GitOps."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.infrastructure.auth.jwt_token_service import JwtTokenService
from src.infrastructure.fastapi.dependencies import get_usuarios_repository
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.settings.config import get_settings

PLANTA_DURAX_ID = "c64fd625-0037-4caa-b68a-800e8e0ee548"
ORG_DURAX_ID = "cf82b4be-0798-4beb-8978-2a27612d5761"


def _crear_token(rol: str, exp_minutos: int = 60) -> str:
    settings = get_settings()
    token_service = JwtTokenService(settings.API_SECRET_KEY)
    expira = datetime.now(timezone.utc) + timedelta(minutes=exp_minutos)
    return token_service.generar(
        usuario_id="user-test-uuid",
        usuario="test@datamaq.com.ar",
        rol=rol,
        expira_en=expira,
        organizacion_id=ORG_DURAX_ID,
    )


@pytest.fixture
def client():
    settings = get_settings()
    app = create_app(settings)
    mock_users_repo = MagicMock()
    mock_usuario = MagicMock()
    mock_usuario.esta_activo = True
    mock_usuario.tokens_revocados_antes_de = None
    mock_usuario.sesiones_revocadas_antes_de = None
    mock_users_repo.buscar_por_id.return_value = mock_usuario
    mock_users_repo.obtener_por_id.return_value = mock_usuario
    app.dependency_overrides[get_usuarios_repository] = lambda: mock_users_repo
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_endpoint_balance_energia_normal(client):
    token = _crear_token(rol="admin")
    resp = client.get(
        f"/api/v1/sge/plantas/{PLANTA_DURAX_ID}/balance-energia",
        params={
            "energia_padre_kwh": 1000.0,
            "energias_hijos_kwh": [600.0, 380.0],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["plantaId"] == PLANTA_DURAX_ID
    assert data["estado"] == "CONCILIADO_NORMAL"
    assert data["esAuditableIso50001"] is True
    assert data["residualKwh"] == 20.0
    assert data["residualPorcentual"] == 0.02


def test_endpoint_balance_energia_con_armonicos_thd(client):
    token = _crear_token(rol="ingeniero")
    resp = client.get(
        f"/api/v1/sge/plantas/{PLANTA_DURAX_ID}/balance-energia",
        params={
            "energia_padre_kwh": 1000.0,
            "energias_hijos_kwh": [500.0, 430.0],  # 7% residual
            "thd_i_promedio_pct": 21.5,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["estado"] == "PERDIDAS_ELEVADAS_POR_ARMONICOS"
    assert data["esAuditableIso50001"] is True
    assert data["thdIPromedioPct"] == 21.5
    assert "distorsión armónica" in data["detalle"]


def test_endpoint_ahorros_cusum(client):
    token = _crear_token(rol="admin")
    resp = client.get(
        f"/api/v1/sge/plantas/{PLANTA_DURAX_ID}/ahorros-cusum",
        params={
            "unidades_producidas": 1000.0,
            "horas_periodo": 8.0,
            "energia_real_kwh": 200.0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["plantaId"] == PLANTA_DURAX_ID
    assert data["lineaBaseId"] == "enb-durax-usina-2026"
    assert "ahorroTotalKwh" in data
    assert "puntosCusum" in data
    assert len(data["puntosCusum"]) >= 1


def test_endpoint_lineas_base_gitops(client):
    token = _crear_token(rol="operador")
    resp = client.get(
        f"/api/v1/sge/plantas/{PLANTA_DURAX_ID}/linea-base",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    enb = data[0]
    assert enb["id"] == "enb-durax-usina-2026"
    assert enb["nodoNombre"] == "TGBT Usina"
    assert enb["secReferenciaKwhUnidad"] == 0.125
    assert enb["potenciaBaseKw"] == 15.0
    assert enb["autorizadoPor"] == "admin@durax.com.ar"
    assert enb["activa"] is True
