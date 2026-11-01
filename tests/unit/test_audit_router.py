"""tests/unit/test_audit_router.py — Tests para router de auditoría."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.application.dtos.audit_dto import AuditLogDTO
from src.infrastructure.fastapi.dependencies import (
    get_consultar_auditoria_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.settings.config import get_settings


@pytest.fixture()
def client() -> TestClient:
    app = create_app(get_settings())
    return TestClient(app)


def test_audit_logs_acceso_superadmin(client: TestClient):
    app = client.app
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "u-admin", "rol": "superadmin"}

    mock_use_case = MagicMock()
    mock_use_case.ejecutar.return_value = [
        AuditLogDTO(
            id="audit-1",
            registrado_en=datetime.now(timezone.utc),
            categoria="AUTH",
            accion="LOGIN_EXITOSO",
            resultado="EXITO",
        )
    ]
    app.dependency_overrides[get_consultar_auditoria_use_case] = lambda: mock_use_case

    try:
        resp = client.get("/api/v1/audit/logs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "audit-1"
        assert data[0]["categoria"] == "AUTH"
    finally:
        app.dependency_overrides.clear()


def test_audit_logs_rechaza_operador(client: TestClient):
    app = client.app
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "u-op", "rol": "operador"}

    try:
        resp = client.get("/api/v1/audit/logs")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "forbidden"
    finally:
        app.dependency_overrides.clear()
