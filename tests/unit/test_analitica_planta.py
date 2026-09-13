from fastapi.testclient import TestClient

from src.infrastructure.fastapi.dependencies import get_usuario_actual
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.settings.config import get_settings


def mock_get_usuario_actual():
    return {
        "user_id": "usr-test-123",
        "organizacion_id": "org-garin",
        "sub": "usr-test-123",
    }


def test_obtener_banco_capacitores_planta_exito():
    app = create_app(get_settings())
    app.dependency_overrides[get_usuario_actual] = mock_get_usuario_actual

    client = TestClient(app)
    response = client.get("/api/v1/analitica/banco-capacitores/planta?planta_id=planta-garin")
    assert response.status_code == 200
    data = response.json()
    assert data["planta_id"] == "planta-garin"
    assert data["periodo_dias"] == 7
    assert data["fp_promedio"] == 0.88
    assert data["banco_comercial_sugerido_kvar"] > 0
    assert len(data["escalones_sugeridos_kvar"]) > 0


def test_obtener_penalizaciones_planta_exito():
    app = create_app(get_settings())
    app.dependency_overrides[get_usuario_actual] = mock_get_usuario_actual

    client = TestClient(app)
    response = client.get("/api/v1/analitica/penalizaciones/planta?planta_id=planta-garin")
    assert response.status_code == 200
    data = response.json()
    assert data["planta_id"] == "planta-garin"
    assert data["periodo_dias"] == 7
    assert data["horas_bajo_fp"] == 14.5
    assert data["penalizacion_estimada_ars"] > 0
    assert data["moneda"] == "ARS"
