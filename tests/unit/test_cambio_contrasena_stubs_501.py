"""tests/unit/test_cambio_contrasena_stubs_501.py — los endpoints de cambio de contraseña con código
no están implementados: responden 501 y NO registran auditoría de un cambio que no ocurrió.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.infrastructure.fastapi.dependencies import (
    get_registrar_auditoria_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.server import create_app

CLAIMS = {"sub": "u-1", "email": "usuario@example.com", "rol": "operador", "org": "org-a"}


@pytest.fixture()
def auditoria() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def cliente(auditoria: MagicMock) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_usuario_actual] = lambda: CLAIMS
    app.dependency_overrides[get_registrar_auditoria_use_case] = lambda: auditoria
    return TestClient(app)


@pytest.mark.parametrize(
    "ruta",
    ["/api/v1/auth/request-password-change-code", "/api/v1/auth/confirm-password-change"],
)
def test_endpoint_responde_501_sin_auditar(cliente: TestClient, auditoria: MagicMock, ruta: str) -> None:
    respuesta = cliente.patch(ruta, json={"password_actual": "SomePass123", "codigo": "1234"})

    assert respuesta.status_code == 501
    auditoria.ejecutar.assert_not_called()
