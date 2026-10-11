"""tests/unit/test_alertas_router.py — Tests unitarios para el router de alertas de telemetría."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dtos.alerta_dto import AlertaResponseDTO
from src.domain.telemetria.exceptions import AlertaNoEncontradaError
from src.infrastructure.fastapi.dependencies import (
    get_alertas_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.device_ownership import verificar_propiedad_alerta
from src.infrastructure.fastapi.server import create_app

AHORA = datetime(2026, 9, 12, 10, 0, 0, tzinfo=timezone.utc)
RESUELTA_EN = datetime(2026, 9, 12, 11, 30, 0, tzinfo=timezone.utc)
MEDIDOR_ID = "d48c49f0-3564-4000-8000-000000000001"


def _alerta_response_dto(**kwargs) -> AlertaResponseDTO:
    base = {
        "id": 1,
        "dispositivo_id": MEDIDOR_ID,
        "tipo_alerta": "TENSION_ALTA",
        "severidad": "WARNING",
        "mensaje": "Tensión por encima del límite establecido (245.5V > 240.0V)",
        "esta_resuelta": False,
        "disparada_en": AHORA,
        "resuelta_en": None,
        "fase": "R",
        "valor_medido": 245.5,
        "valor_umbral": 240.0,
        "unidad": "V",
        "categoria": "ELECTRICA",
        "duracion_segundos": 120.0,
        "observaciones": None,
    }
    base.update(kwargs)
    return AlertaResponseDTO(**base)


def _cliente(rol: str = "admin", autenticado: bool = True) -> tuple[TestClient, dict[str, MagicMock]]:
    app = create_app()
    mocks = {
        "alertas": MagicMock(),
    }
    app.dependency_overrides[get_alertas_use_case] = lambda: mocks["alertas"]
    # La propiedad de la alerta se prueba en test_aislamiento_alertas.py.
    app.dependency_overrides[verificar_propiedad_alerta] = lambda: None
    if autenticado:
        app.dependency_overrides[get_usuario_actual] = lambda: {
            "sub": "user-test-1",
            "rol": rol,
            "org": "org-test-1",
        }
    return TestClient(app), mocks


# ==============================================================================
# LISTADO DE ALERTAS (GET /api/v1/alertas)
# ==============================================================================


def test_listar_alertas_sin_filtros_retorna_lista():
    client, mocks = _cliente()
    alerta_esperada = _alerta_response_dto()
    mocks["alertas"].listar_alertas.return_value = [alerta_esperada]

    response = client.get("/api/v1/alertas")

    assert response.status_code == 200
    mocks["alertas"].listar_alertas.assert_called_once_with(
        dispositivo_id=None,
        solo_abiertas=False,
        severidad=None,
        limite=100,
        desde=None,
        hasta=None,
        organizacion_id="org-test-1",
        planta_id=None,
    )
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 1
    assert data[0]["dispositivo_id"] == MEDIDOR_ID
    assert data[0]["tipo_alerta"] == "TENSION_ALTA"
    assert data[0]["severidad"] == "WARNING"
    assert data[0]["esta_resuelta"] is False


def test_listar_alertas_lista_vacia():
    client, mocks = _cliente()
    mocks["alertas"].listar_alertas.return_value = []

    response = client.get("/api/v1/alertas")

    assert response.status_code == 200
    assert response.json() == []


def test_listar_alertas_filtro_device_id():
    client, mocks = _cliente()
    mocks["alertas"].listar_alertas.return_value = [_alerta_response_dto(dispositivo_id="dev-xyz-999")]

    response = client.get("/api/v1/alertas?device_id=dev-xyz-999")

    assert response.status_code == 200
    mocks["alertas"].listar_alertas.assert_called_once_with(
        dispositivo_id="dev-xyz-999",
        solo_abiertas=False,
        severidad=None,
        limite=100,
        desde=None,
        hasta=None,
        organizacion_id="org-test-1",
        planta_id=None,
    )
    data = response.json()
    assert data[0]["dispositivo_id"] == "dev-xyz-999"


def test_listar_alertas_filtro_solo_abiertas_true():
    client, mocks = _cliente()
    mocks["alertas"].listar_alertas.return_value = [_alerta_response_dto(esta_resuelta=False)]

    response = client.get("/api/v1/alertas?solo_abiertas=true")

    assert response.status_code == 200
    mocks["alertas"].listar_alertas.assert_called_once_with(
        dispositivo_id=None,
        solo_abiertas=True,
        severidad=None,
        limite=100,
        desde=None,
        hasta=None,
        organizacion_id="org-test-1",
        planta_id=None,
    )


def test_listar_alertas_filtro_solo_abiertas_false():
    client, mocks = _cliente()
    mocks["alertas"].listar_alertas.return_value = [_alerta_response_dto(esta_resuelta=True)]

    response = client.get("/api/v1/alertas?solo_abiertas=false")

    assert response.status_code == 200
    mocks["alertas"].listar_alertas.assert_called_once_with(
        dispositivo_id=None,
        solo_abiertas=False,
        severidad=None,
        limite=100,
        desde=None,
        hasta=None,
        organizacion_id="org-test-1",
        planta_id=None,
    )


def test_listar_alertas_filtro_severidad():
    client, mocks = _cliente()
    mocks["alertas"].listar_alertas.return_value = [_alerta_response_dto(severidad="CRITICAL")]

    response = client.get("/api/v1/alertas?severidad=CRITICAL")

    assert response.status_code == 200
    mocks["alertas"].listar_alertas.assert_called_once_with(
        dispositivo_id=None,
        solo_abiertas=False,
        severidad="CRITICAL",
        limite=100,
        desde=None,
        hasta=None,
        organizacion_id="org-test-1",
        planta_id=None,
    )
    assert response.json()[0]["severidad"] == "CRITICAL"


def test_listar_alertas_filtro_limit_personalizado():
    client, mocks = _cliente()
    mocks["alertas"].listar_alertas.return_value = []

    response = client.get("/api/v1/alertas?limit=50")

    assert response.status_code == 200
    mocks["alertas"].listar_alertas.assert_called_once_with(
        dispositivo_id=None,
        solo_abiertas=False,
        severidad=None,
        limite=50,
        desde=None,
        hasta=None,
        organizacion_id="org-test-1",
        planta_id=None,
    )


def test_listar_alertas_filtro_limit_maximo_permitido():
    client, mocks = _cliente()
    mocks["alertas"].listar_alertas.return_value = []

    response = client.get("/api/v1/alertas?limit=500")

    assert response.status_code == 200
    mocks["alertas"].listar_alertas.assert_called_once_with(
        dispositivo_id=None,
        solo_abiertas=False,
        severidad=None,
        limite=500,
        desde=None,
        hasta=None,
        organizacion_id="org-test-1",
        planta_id=None,
    )


def test_listar_alertas_filtro_limit_excede_maximo():
    client, mocks = _cliente()

    response = client.get("/api/v1/alertas?limit=501")

    assert response.status_code == 422
    mocks["alertas"].listar_alertas.assert_not_called()


def test_listar_alertas_filtro_fechas_desde_hasta():
    client, mocks = _cliente()
    mocks["alertas"].listar_alertas.return_value = []

    response = client.get("/api/v1/alertas?desde=2026-09-01T00:00:00Z&hasta=2026-09-10T23:59:59Z")

    assert response.status_code == 200
    mocks["alertas"].listar_alertas.assert_called_once_with(
        dispositivo_id=None,
        solo_abiertas=False,
        severidad=None,
        limite=100,
        desde=datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc),
        hasta=datetime(2026, 9, 10, 23, 59, 59, tzinfo=timezone.utc),
        organizacion_id="org-test-1",
        planta_id=None,
    )


def test_listar_alertas_filtro_fecha_invalida():
    client, mocks = _cliente()

    response = client.get("/api/v1/alertas?desde=fecha-invalida")

    assert response.status_code == 422
    mocks["alertas"].listar_alertas.assert_not_called()


def test_listar_alertas_combinacion_todos_los_filtros():
    client, mocks = _cliente()
    mocks["alertas"].listar_alertas.return_value = [_alerta_response_dto()]

    response = client.get(
        "/api/v1/alertas?device_id=dev-combo-1&solo_abiertas=true&severidad=INFO&limit=25"
        "&desde=2026-09-05T08:00:00Z&hasta=2026-09-06T18:00:00Z"
    )

    assert response.status_code == 200
    mocks["alertas"].listar_alertas.assert_called_once_with(
        dispositivo_id="dev-combo-1",
        solo_abiertas=True,
        severidad="INFO",
        limite=25,
        desde=datetime(2026, 9, 5, 8, 0, 0, tzinfo=timezone.utc),
        hasta=datetime(2026, 9, 6, 18, 0, 0, tzinfo=timezone.utc),
        organizacion_id="org-test-1",
        planta_id=None,
    )


def test_listar_alertas_filtro_planta_id():
    client, mocks = _cliente()
    mocks["alertas"].listar_alertas.return_value = [_alerta_response_dto()]

    response = client.get("/api/v1/alertas?planta_id=planta-garin")

    assert response.status_code == 200
    mocks["alertas"].listar_alertas.assert_called_once_with(
        dispositivo_id=None,
        solo_abiertas=False,
        severidad=None,
        limite=100,
        desde=None,
        hasta=None,
        organizacion_id="org-test-1",
        planta_id="planta-garin",
    )


def test_listar_alertas_rol_invitado_permitido():
    client, mocks = _cliente(rol="invitado")
    mocks["alertas"].listar_alertas.return_value = [_alerta_response_dto()]

    response = client.get("/api/v1/alertas")

    assert response.status_code == 200


# ==============================================================================
# RESOLVER ALERTA VÍA POST (/api/v1/alertas/{alerta_id}/resolver)
# ==============================================================================


def test_resolver_alerta_post_con_observaciones():
    client, mocks = _cliente()
    alerta_resuelta = _alerta_response_dto(
        id=1,
        esta_resuelta=True,
        resuelta_en=RESUELTA_EN,
        observaciones="Fusible de protección reemplazado",
    )
    mocks["alertas"].resolver_alerta.return_value = alerta_resuelta

    response = client.post(
        "/api/v1/alertas/1/resolver",
        json={"observaciones": "Fusible de protección reemplazado"},
    )

    assert response.status_code == 200
    mocks["alertas"].resolver_alerta.assert_called_once_with(
        1,
        observaciones="Fusible de protección reemplazado",
    )
    data = response.json()
    assert data["id"] == 1
    assert data["esta_resuelta"] is True
    assert data["observaciones"] == "Fusible de protección reemplazado"


def test_resolver_alerta_post_sin_body():
    client, mocks = _cliente()
    alerta_resuelta = _alerta_response_dto(
        id=1,
        esta_resuelta=True,
        resuelta_en=RESUELTA_EN,
        observaciones=None,
    )
    mocks["alertas"].resolver_alerta.return_value = alerta_resuelta

    response = client.post("/api/v1/alertas/1/resolver")

    assert response.status_code == 200
    mocks["alertas"].resolver_alerta.assert_called_once_with(1, observaciones=None)
    data = response.json()
    assert data["esta_resuelta"] is True
    assert data["observaciones"] is None


def test_resolver_alerta_post_body_vacio():
    client, mocks = _cliente()
    alerta_resuelta = _alerta_response_dto(
        id=1,
        esta_resuelta=True,
        resuelta_en=RESUELTA_EN,
        observaciones=None,
    )
    mocks["alertas"].resolver_alerta.return_value = alerta_resuelta

    response = client.post("/api/v1/alertas/1/resolver", json={})

    assert response.status_code == 200
    mocks["alertas"].resolver_alerta.assert_called_once_with(1, observaciones=None)


def test_resolver_alerta_post_no_encontrada_retorna_404():
    client, mocks = _cliente()
    mocks["alertas"].resolver_alerta.side_effect = AlertaNoEncontradaError("Alerta con ID 999 no encontrada.")

    response = client.post("/api/v1/alertas/999/resolver")

    assert response.status_code == 404
    data = response.json()
    assert "Alerta con ID 999 no encontrada" in data["detail"]


def test_resolver_alerta_post_error_inesperado_retorna_500():
    client, mocks = _cliente()
    mocks["alertas"].resolver_alerta.side_effect = RuntimeError("Error imprevisto en la base de datos")

    response = client.post("/api/v1/alertas/1/resolver")

    assert response.status_code == 500


def test_resolver_alerta_post_id_invalido():
    client, mocks = _cliente()

    response = client.post("/api/v1/alertas/invalido/resolver")

    assert response.status_code == 422
    mocks["alertas"].resolver_alerta.assert_not_called()


def test_resolver_alerta_post_rol_invitado_prohibido():
    client, mocks = _cliente(rol="invitado")

    response = client.post("/api/v1/alertas/1/resolver")

    assert response.status_code == 403
    mocks["alertas"].resolver_alerta.assert_not_called()


def test_resolver_alerta_post_rol_invitado_global_prohibido():
    client, mocks = _cliente(rol="invitado_global")

    response = client.post("/api/v1/alertas/1/resolver")

    assert response.status_code == 403
    mocks["alertas"].resolver_alerta.assert_not_called()


def test_resolver_alerta_post_rol_operador_permitido():
    client, mocks = _cliente(rol="operador")
    alerta_resuelta = _alerta_response_dto(id=1, esta_resuelta=True, resuelta_en=RESUELTA_EN)
    mocks["alertas"].resolver_alerta.return_value = alerta_resuelta

    response = client.post("/api/v1/alertas/1/resolver")

    assert response.status_code == 200
    mocks["alertas"].resolver_alerta.assert_called_once_with(1, observaciones=None)


# ==============================================================================
# RESOLVER ALERTA VÍA PATCH (/api/v1/alertas/{alerta_id}/resolver)
# ==============================================================================


def test_resolver_alerta_patch_con_observaciones():
    client, mocks = _cliente()
    alerta_resuelta = _alerta_response_dto(
        id=2,
        esta_resuelta=True,
        resuelta_en=RESUELTA_EN,
        observaciones="Resuelto vía PATCH tras inspección",
    )
    mocks["alertas"].resolver_alerta.return_value = alerta_resuelta

    response = client.patch(
        "/api/v1/alertas/2/resolver",
        json={"observaciones": "Resuelto vía PATCH tras inspección"},
    )

    assert response.status_code == 200
    mocks["alertas"].resolver_alerta.assert_called_once_with(
        2,
        observaciones="Resuelto vía PATCH tras inspección",
    )
    data = response.json()
    assert data["id"] == 2
    assert data["esta_resuelta"] is True
    assert data["observaciones"] == "Resuelto vía PATCH tras inspección"


def test_resolver_alerta_patch_sin_body():
    client, mocks = _cliente()
    alerta_resuelta = _alerta_response_dto(
        id=2,
        esta_resuelta=True,
        resuelta_en=RESUELTA_EN,
        observaciones=None,
    )
    mocks["alertas"].resolver_alerta.return_value = alerta_resuelta

    response = client.patch("/api/v1/alertas/2/resolver")

    assert response.status_code == 200
    mocks["alertas"].resolver_alerta.assert_called_once_with(2, observaciones=None)
    data = response.json()
    assert data["esta_resuelta"] is True


def test_resolver_alerta_patch_body_vacio():
    client, mocks = _cliente()
    alerta_resuelta = _alerta_response_dto(
        id=2,
        esta_resuelta=True,
        resuelta_en=RESUELTA_EN,
        observaciones=None,
    )
    mocks["alertas"].resolver_alerta.return_value = alerta_resuelta

    response = client.patch("/api/v1/alertas/2/resolver", json={})

    assert response.status_code == 200
    mocks["alertas"].resolver_alerta.assert_called_once_with(2, observaciones=None)


def test_resolver_alerta_patch_no_encontrada_retorna_404():
    client, mocks = _cliente()
    mocks["alertas"].resolver_alerta.side_effect = AlertaNoEncontradaError("Alerta con ID 404 no encontrada.")

    response = client.patch("/api/v1/alertas/404/resolver")

    assert response.status_code == 404
    data = response.json()
    assert "Alerta con ID 404 no encontrada" in data["detail"]


def test_resolver_alerta_patch_error_inesperado_retorna_500():
    client, mocks = _cliente()
    mocks["alertas"].resolver_alerta.side_effect = RuntimeError("Error inesperado")

    response = client.patch("/api/v1/alertas/2/resolver")

    assert response.status_code == 500


def test_resolver_alerta_patch_rol_invitado_prohibido():
    client, mocks = _cliente(rol="invitado")

    response = client.patch("/api/v1/alertas/2/resolver")

    assert response.status_code == 403
    mocks["alertas"].resolver_alerta.assert_not_called()


def test_resolver_alerta_patch_rol_operador_permitido():
    client, mocks = _cliente(rol="operador")
    alerta_resuelta = _alerta_response_dto(id=2, esta_resuelta=True, resuelta_en=RESUELTA_EN)
    mocks["alertas"].resolver_alerta.return_value = alerta_resuelta

    response = client.patch("/api/v1/alertas/2/resolver")

    assert response.status_code == 200
    mocks["alertas"].resolver_alerta.assert_called_once_with(2, observaciones=None)
