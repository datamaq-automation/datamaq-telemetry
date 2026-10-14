"""Endpoint /analitica/penalizaciones/planta por período de facturación (sin ventana de telemetría)."""

from fastapi.testclient import TestClient

from src.domain.telemetria.penalizacion_periodo import MOTIVO_PERIODO_SIN_TARIFA
from src.infrastructure.fastapi.dependencies import get_usuario_actual
from src.infrastructure.fastapi.planta_ownership import resolver_planta_permitida
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.settings.config import get_settings

PLANTA_DURAX = "c64fd625-0037-4caa-b68a-800e8e0ee548"
PLANTA_UPP = "4f68f653-a604-4834-8154-31f938248572"
RUTA = "/api/v1/analitica/penalizaciones/planta"


def _cliente() -> TestClient:
    app = create_app(get_settings())
    app.dependency_overrides[get_usuario_actual] = lambda: {
        "user_id": "usr-test-123",
        "organizacion_id": "org-test",
        "sub": "usr-test-123",
    }
    app.dependency_overrides[resolver_planta_permitida] = lambda planta_id=None: planta_id
    return TestClient(app)


def test_periodo_con_factura_durax_expone_recargo_con_distribuidora_tarifa_y_fuente():
    response = _cliente().get(f"{RUTA}?planta_id={PLANTA_DURAX}&periodo_facturacion=2025-07")

    assert response.status_code == 200
    data = response.json()
    assert data["disponible"] is True
    assert data["periodo_facturacion"] == "2025-07"
    assert data["distribuidora"] == "Edesur"
    assert data["tarifa"] == "T3 MT"
    assert data["fuente_archivo"] == "Cristal Avellaneda - EDESUR/2025-07.pdf"
    assert data["concepto"]
    # La factura dice 508.010,91; el cálculo da 508.010,92 (centavo de redondeo de la distribuidora).
    assert round(data["penalizacion_estimada_ars"], 2) == 508010.92
    assert data["motivo_no_disponible"] is None


def test_periodo_con_factura_upp_reactiva_bajo_limite_da_cero():
    response = _cliente().get(f"{RUTA}?planta_id={PLANTA_UPP}&periodo_facturacion=2024-08")

    assert response.status_code == 200
    data = response.json()
    assert data["disponible"] is True
    assert data["penalizacion_estimada_ars"] == 0.0
    assert data["distribuidora"] == "EDELAP"
    assert data["tarifa"] == "T5M12"
    assert data["fuente_archivo"] == "Papelera platense - EDELAP/2024-08.pdf"


def test_periodo_sin_factura_verificada_devuelve_null_con_motivo_sin_inventar():
    response = _cliente().get(f"{RUTA}?planta_id={PLANTA_DURAX}&periodo_facturacion=2025-06")

    assert response.status_code == 200
    data = response.json()
    assert data["disponible"] is False
    assert data["penalizacion_estimada_ars"] is None
    assert data["motivo_no_disponible"] == MOTIVO_PERIODO_SIN_TARIFA
    assert data["distribuidora"] is None
    assert data["fuente_archivo"] is None


def test_periodo_con_formato_invalido_responde_422():
    response = _cliente().get(f"{RUTA}?planta_id={PLANTA_DURAX}&periodo_facturacion=2025-7")

    assert response.status_code == 422


def test_sin_periodo_facturacion_la_respuesta_por_ventana_no_cambia():
    response = _cliente().get(f"{RUTA}?planta_id={PLANTA_DURAX}&periodo_dias=7")

    assert response.status_code == 200
    data = response.json()
    assert data["periodo_facturacion"] is None
    assert data["concepto"] is None
    assert data["penalizacion_estimada_ars"] is None
