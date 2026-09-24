# tests/unit/test_copilot_router.py
from fastapi.testclient import TestClient

from src.infrastructure.fastapi.dependencies import get_usuario_actual
from src.infrastructure.fastapi.routes.copilot_router import router as copilot_router
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.settings.config import get_settings


def mock_get_usuario_actual():
    return {
        "user_id": "usr-test-123",
        "organizacion_id": "org-garin",
        "sub": "usr-test-123",
    }


def test_copilot_chat_endpoint_exito():
    app = create_app(get_settings())
    app.include_router(copilot_router)
    app.dependency_overrides[get_usuario_actual] = mock_get_usuario_actual

    client = TestClient(app)
    payload = {
        "mensaje": "¿Por qué tengo alerta de bajo factor de potencia en el Medidor 1?",
        "dispositivo_id": "dev-01-garin",
        "historial_contexto": [
            {"rol": "usuario", "texto": "¿Cuáles son los dispositivos activos?"},
            {"rol": "asistente", "texto": "Tenés 3 medidores registrados en la planta Garín."},
        ],
    }

    response = client.post("/api/v1/copilot/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "mensaje_id" in data
    assert "0.88" in data["respuesta"]
    assert data["diagnostico_adjunto"]["requiere_accion"] is True
    assert data["diagnostico_adjunto"]["sugerencia_kvar"] == 15.0
    assert data["diagnostico_adjunto"]["alerta_relacionada_id"] == 1045
