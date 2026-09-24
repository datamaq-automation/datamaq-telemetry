"""tests/unit/test_chat_apagado.py — Los endpoints de chat no están expuestos hasta aislarlos por organización (D1)."""

import pytest
from fastapi.testclient import TestClient

from src.infrastructure.fastapi.dependencies import get_usuario_actual
from src.infrastructure.fastapi.server import create_app


@pytest.mark.parametrize("ruta", ["/api/v1/asistente/preguntar", "/api/v1/copilot/chat"])
def test_endpoints_de_chat_responden_404(ruta):
    app = create_app()
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "u1", "rol": "superadmin"}
    response = TestClient(app).post(ruta, json={"pregunta": "hola", "mensaje": "hola"})
    assert response.status_code == 404
