"""tests/integration/test_purga_ruta_superadmin.py — datamaq#119: la ruta HTTP de purga.

Dependencias sobrescritas: caso de uso con repositorio espía y auditoría en memoria.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from src.application.use_cases.purgar_telemetria import PurgarTelemetriaExpiradaUseCase
from src.infrastructure.fastapi.dependencies import (
    get_purga_use_case,
    get_registrar_auditoria_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.server import create_app
from tests.unit.test_purga_cotas_superadmin import SpyRepo

AHORA_TEST = datetime.now(timezone.utc)


class AuditoriaEnMemoria:
    def __init__(self) -> None:
        self.eventos: list = []

    def ejecutar(self, dto) -> None:
        self.eventos.append(dto)


@pytest.fixture
def cliente_y_estado():
    app = create_app()
    repo = SpyRepo()
    auditoria = AuditoriaEnMemoria()
    app.dependency_overrides[get_purga_use_case] = lambda: PurgarTelemetriaExpiradaUseCase(repo)
    app.dependency_overrides[get_registrar_auditoria_use_case] = lambda: auditoria
    claims = {"sub": "u-1", "usuario": "dueno@ejemplo.com", "rol": "superadmin"}
    app.dependency_overrides[get_usuario_actual] = lambda: claims
    cliente = TestClient(app)
    yield cliente, repo, auditoria, claims, app
    app.dependency_overrides.clear()


def test_admin_recibe_403(cliente_y_estado) -> None:
    cliente, repo, _, claims, _ = cliente_y_estado
    claims["rol"] = "admin"
    resp = cliente.post("/api/v1/system/purge", json={})
    assert resp.status_code == 403
    assert repo.borrados == []


def test_sin_confirmar_simula_y_no_borra(cliente_y_estado) -> None:
    cliente, repo, auditoria, _, _ = cliente_y_estado
    resp = cliente.post("/api/v1/system/purge", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["simulado"] is True
    assert body["total_registros_eliminados"] == 13
    assert repo.borrados == []
    assert auditoria.eventos[-1].accion == "PURGA_SIMULADA"


def test_confirmar_borra_y_audita(cliente_y_estado) -> None:
    cliente, repo, auditoria, _, _ = cliente_y_estado
    resp = cliente.post("/api/v1/system/purge", json={"confirmar": True})
    assert resp.status_code == 200
    assert resp.json()["simulado"] is False
    assert repo.borrados  # se intentó borrar
    evento = auditoria.eventos[-1]
    assert evento.accion == "PURGA_EJECUTADA"
    assert evento.categoria == "SISTEMA"
    assert evento.actor_usuario_id == "u-1"


@pytest.mark.parametrize("cuerpo", [{"dias_retencion_override": 0}, {"dias_retencion_override": -5}])
def test_cero_y_negativos_dan_422(cliente_y_estado, cuerpo) -> None:
    cliente, repo, _, _, _ = cliente_y_estado
    resp = cliente.post("/api/v1/system/purge", json={**cuerpo, "confirmar": True})
    assert resp.status_code == 422
    assert repo.borrados == []


def test_override_bajo_el_piso_exige_confirmacion_de_retencion(cliente_y_estado) -> None:
    cliente, repo, _, _, _ = cliente_y_estado
    resp = cliente.post("/api/v1/system/purge", json={"dias_retencion_override": 30, "confirmar": True})
    assert resp.status_code == 422
    assert repo.borrados == []

    ok = cliente.post(
        "/api/v1/system/purge",
        json={"dias_retencion_override": 30, "confirmar": True, "confirmar_retencion_menor": True},
    )
    assert ok.status_code == 200


def test_corte_hasta_futuro_da_422(cliente_y_estado) -> None:
    cliente, repo, _, _, _ = cliente_y_estado
    futuro = datetime(2100, 1, 1, tzinfo=timezone.utc).isoformat()
    resp = cliente.post("/api/v1/system/purge", json={"corte_hasta": futuro, "confirmar": True})
    assert resp.status_code == 422
    assert repo.borrados == []


class AuditoriaQueFalla:
    def ejecutar(self, dto) -> None:
        raise RuntimeError("auditoría caída")


def test_override_40_con_energia_2000_y_confirmar_da_422(cliente_y_estado) -> None:
    cliente, repo, _, _, _ = cliente_y_estado
    resp = cliente.post(
        "/api/v1/system/purge",
        json={
            "dias_retencion_override": 40,
            "dias_retencion_instantaneas": 100,
            "dias_retencion_energia": 2000,
            "confirmar": True,
        },
    )
    assert resp.status_code == 422
    assert repo.borrados == []


def test_corte_hasta_reciente_con_confirmar_da_422(cliente_y_estado) -> None:
    cliente, repo, _, _, _ = cliente_y_estado
    reciente = (AHORA_TEST - timedelta(days=10)).isoformat()
    resp = cliente.post("/api/v1/system/purge", json={"corte_hasta": reciente, "confirmar": True})
    assert resp.status_code == 422
    assert repo.borrados == []


def test_auditoria_de_intencion_que_falla_no_borra(cliente_y_estado) -> None:
    cliente, repo, _, _, app = cliente_y_estado
    app.dependency_overrides[get_registrar_auditoria_use_case] = lambda: AuditoriaQueFalla()
    resp = cliente.post("/api/v1/system/purge", json={"confirmar": True})
    assert resp.status_code >= 500
    assert repo.borrados == []


def test_confirmar_sin_auditoria_no_borra(cliente_y_estado) -> None:
    cliente, repo, _, _, app = cliente_y_estado
    app.dependency_overrides[get_registrar_auditoria_use_case] = lambda: None
    resp = cliente.post("/api/v1/system/purge", json={"confirmar": True})
    assert resp.status_code >= 500
    assert repo.borrados == []


def test_confirmar_registra_intencion_antes_y_resultado_despues(cliente_y_estado) -> None:
    cliente, _, auditoria, _, _ = cliente_y_estado
    resp = cliente.post("/api/v1/system/purge", json={"confirmar": True})
    assert resp.status_code == 200
    acciones = [e.accion for e in auditoria.eventos]
    assert acciones == ["PURGA_SOLICITADA", "PURGA_EJECUTADA"]
