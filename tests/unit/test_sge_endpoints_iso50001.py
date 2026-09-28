"""tests/unit/test_sge_endpoints_iso50001.py — Tests para endpoints de Balance, CUSUM y EnB GitOps."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.application.use_cases.gestionar_acceso_plantas import GestionarAccesoPlantasUseCase
from src.infrastructure.auth.jwt_token_service import JwtTokenService
from src.infrastructure.fastapi.auth_dependencies import get_acceso_plantas_use_case
from src.infrastructure.fastapi.dependencies import get_usuarios_repository
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.settings.config import get_settings
from src.infrastructure.yaml.repositories.organizaciones_repository import YamlOrganizacionesRepository

PLANTA_DURAX_ID = "c64fd625-0037-4caa-b68a-800e8e0ee548"
ORG_DURAX_ID = "cf82b4be-0798-4beb-8978-2a27612d5761"
PLANTA_UPP_ID = "4f68f653-a604-4834-8154-31f938248572"
ORG_UPP_ID = "edebb9a0-85e5-4bde-a370-e64bd9b9608c"


def _crear_token(rol: str, exp_minutos: int = 60, organizacion_id: str = ORG_DURAX_ID) -> str:
    settings = get_settings()
    token_service = JwtTokenService(settings.API_SECRET_KEY)
    expira = datetime.now(timezone.utc) + timedelta(minutes=exp_minutos)
    return token_service.generar(
        usuario_id="user-test-uuid",
        usuario="test@datamaq.com.ar",
        rol=rol,
        expira_en=expira,
        organizacion_id=organizacion_id,
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
    # Política de acceso real contra el YAML, sin asignaciones: no depende de MySQL.
    repo_accesos = MagicMock()
    repo_accesos.listar_por_usuario.return_value = []
    app.dependency_overrides[get_acceso_plantas_use_case] = lambda: GestionarAccesoPlantasUseCase(
        repo_accesos, YamlOrganizacionesRepository()
    )
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


def test_endpoint_facturas_distribuidora_gitops(client):
    token = _crear_token(rol="operador", organizacion_id=ORG_UPP_ID)
    resp = client.get(
        f"/api/v1/sge/plantas/{PLANTA_UPP_ID}/facturas-distribuidora",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    # UPP: facturas reales de potencia de EdeLAP (ver data/facturas_distribuidora.yml). Corregido
    # 2026-09-28: el test afirmaba un par EDELAP+CAMMESA "2026-08" que en realidad era la factura
    # EdeLAP 2024-11 mal fechada más una fila de CAMMESA armada a mano. Ya no están en el YAML.
    assert len(data) >= 12
    assert all(f["plantaId"] == PLANTA_UPP_ID for f in data)
    assert not [f for f in data if f["periodo"] == "2026-08"]

    potencia = next(f for f in data if f["periodo"] == "2024-11")
    assert potencia["tipoDato"] == "potencia"
    assert potencia["proveedor"] == "EDELAP"
    assert potencia["tarifa"] == "T5M12"
    assert potencia["numeroFactura"] == "0020-01988580"
    assert potencia["potenciaExcedidaPuntaKw"] == pytest.approx(249.0)
    assert potencia["potenciaExcedidaFueraPuntaKw"] == pytest.approx(232.0)
    assert potencia["importeTotalArs"] == pytest.approx(21031736.78)

    # 2024-02: mes sin exceso de potencia (demanda registrada por debajo de la contratada).
    sin_exceso = next(f for f in data if f["periodo"] == "2024-02")
    assert sin_exceso["potenciaAdquiridaPuntaKw"] == pytest.approx(508.0)
    assert sin_exceso["potenciaExcedidaPuntaKw"] == pytest.approx(0.0)


def test_endpoint_facturas_distribuidora_planta_inexistente_404(client):
    token = _crear_token(rol="operador")
    resp = client.get(
        "/api/v1/sge/plantas/planta-que-no-existe/facturas-distribuidora",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
