"""tests/unit/test_dispositivos_router.py — Tests unitarios para el router de dispositivos."""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.application.dtos.dispositivo_dto import DispositivoResponseDTO
from src.domain.telemetria.exceptions import (
    DispositivoNoEncontradoError,
    LimiteDispositivosExcedidoError,
)
from src.infrastructure.fastapi.auth_dependencies import get_acceso_plantas_use_case
from src.infrastructure.fastapi.dependencies import (
    get_dispositivos_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.device_ownership import verificar_propiedad_dispositivo
from src.infrastructure.fastapi.planta_ownership import resolver_planta_permitida
from src.infrastructure.fastapi.server import create_app

AHORA = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)


def _dispositivo_dto(**kwargs) -> DispositivoResponseDTO:
    base = {
        "id": "dev-1",
        "device_uid": "00:11:22:33:44:55",
        "nombre": "Medidor Principal",
        "modelo": "SmartPlus",
        "planta_id": "planta-1",
        "numero_serie": "SN123456",
        "version_hw": "v1.0",
        "version_fw": "v2.1",
        "ubicacion_tag": "Tablero A",
        "esta_activo": True,
        "tipo_instalacion": "CONSUMO",
        "fases_con_ti": "R,S,T",
        "estado": "ONLINE",
        "visto_por_ultima_vez": AHORA,
        "creado_en": AHORA,
        "actualizado_en": AHORA,
        "voltage_linea_V": 380.0,
    }
    base.update(kwargs)
    return DispositivoResponseDTO(**base)


def _cliente(
    rol: str = "admin",
    org: str | None = "org-1",
    sub: str = "u1",
    mock_propiedad: bool = True,
    planta_id_permitida: str | None = None,
) -> tuple[TestClient, dict[str, MagicMock]]:
    app = create_app()
    mocks = {
        "dispositivos": MagicMock(),
    }
    app.dependency_overrides[get_dispositivos_use_case] = lambda: mocks["dispositivos"]

    claims: dict[str, Any] = {"sub": sub, "rol": rol}
    if org is not None:
        claims["org"] = org
    app.dependency_overrides[get_usuario_actual] = lambda: claims

    # Mock resolver_planta_permitida para retornar la planta permitida (o None para todas)
    app.dependency_overrides[resolver_planta_permitida] = lambda planta_id=None: planta_id_permitida or planta_id

    if mock_propiedad:
        app.dependency_overrides[verificar_propiedad_dispositivo] = lambda: None

    return TestClient(app), mocks


# ==============================================================================
# 1. LISTAR DISPOSITIVOS (GET /api/v1/dispositivos)
# ==============================================================================


def test_listar_dispositivos_usuario_con_org():
    client, mocks = _cliente(rol="admin", org="org-1")
    mocks["dispositivos"].listar_dispositivos.return_value = [
        _dispositivo_dto(id="dev-1", device_uid="00:11:22:33:44:55"),
        _dispositivo_dto(id="dev-2", device_uid="00:11:22:33:44:56"),
    ]

    response = client.get("/api/v1/dispositivos")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["id"] == "dev-1"
    assert data[1]["id"] == "dev-2"
    mocks["dispositivos"].listar_dispositivos.assert_called_once_with(None, organizacion_id="org-1")


def test_listar_dispositivos_con_filtro_planta():
    client, mocks = _cliente(rol="operador", org="org-1", planta_id_permitida="planta-abc")
    mocks["dispositivos"].listar_dispositivos.return_value = [
        _dispositivo_dto(id="dev-1", planta_id="planta-abc"),
    ]

    response = client.get("/api/v1/dispositivos?planta_id=planta-abc")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["planta_id"] == "planta-abc"
    mocks["dispositivos"].listar_dispositivos.assert_called_once_with("planta-abc", organizacion_id="org-1")


def test_listar_dispositivos_superadmin_sin_filtro_org():
    client, mocks = _cliente(rol="superadmin", org="org-superadmin")
    mocks["dispositivos"].listar_dispositivos.return_value = [_dispositivo_dto()]

    response = client.get("/api/v1/dispositivos")

    assert response.status_code == 200
    mocks["dispositivos"].listar_dispositivos.assert_called_once_with(None, organizacion_id=None)


def test_listar_dispositivos_sin_org_fail_closed():
    client, mocks = _cliente(rol="admin", org=None)

    response = client.get("/api/v1/dispositivos")

    assert response.status_code == 200
    assert response.json() == []
    mocks["dispositivos"].listar_dispositivos.assert_not_called()


# ==============================================================================
# 2. OBTENER DISPOSITIVO (GET /api/v1/dispositivos/{device_id})
# ==============================================================================


def test_obtener_dispositivo_exitoso():
    client, mocks = _cliente()
    mocks["dispositivos"].obtener_dispositivo.return_value = _dispositivo_dto(
        id="dev-123", device_uid="11:22:33:44:55:66", nombre="Medidor Secundario"
    )

    response = client.get("/api/v1/dispositivos/dev-123")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "dev-123"
    assert data["device_uid"] == "11:22:33:44:55:66"
    assert data["nombre"] == "Medidor Secundario"
    mocks["dispositivos"].obtener_dispositivo.assert_called_once_with("dev-123")


def test_obtener_dispositivo_no_encontrado_404():
    client, mocks = _cliente()
    mocks["dispositivos"].obtener_dispositivo.side_effect = DispositivoNoEncontradoError(
        "Dispositivo 'dev-999' no encontrado."
    )

    response = client.get("/api/v1/dispositivos/dev-999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Dispositivo 'dev-999' no encontrado."


def test_obtener_dispositivo_error_inesperado_500():
    client, mocks = _cliente()
    mocks["dispositivos"].obtener_dispositivo.side_effect = RuntimeError("Fallo crítico de base de datos")

    response = client.get("/api/v1/dispositivos/dev-1")

    assert response.status_code == 500


# ==============================================================================
# 3. REGISTRAR DISPOSITIVO (POST /api/v1/dispositivos)
# ==============================================================================


def test_registrar_dispositivo_exitoso():
    client, mocks = _cliente(rol="admin")
    # La planta destino se valida con la política de plantas (datamaq#132): acá la permite.
    acceso = MagicMock()
    acceso.resolver_planta_permitida.return_value = "planta-1"
    client.app.dependency_overrides[get_acceso_plantas_use_case] = lambda: acceso
    mocks["dispositivos"].registrar_dispositivo.return_value = _dispositivo_dto(
        id="dev-nuevo",
        device_uid="00:11:22:33:44:55",
        nombre="Nuevo Medidor",
        modelo="SmartPlus",
        planta_id="planta-1",
    )

    payload = {
        "device_uid": "00:11:22:33:44:55",
        "nombre": "Nuevo Medidor",
        "modelo": "SmartPlus",
        "planta_id": "planta-1",
        "esta_activo": True,
        "tipo_instalacion": "CONSUMO",
        "fases_con_ti": "R,S,T",
    }
    response = client.post("/api/v1/dispositivos", json=payload)

    assert response.status_code == 200
    acceso.resolver_planta_permitida.assert_called_once_with("u1", "admin", "org-1", "planta-1")
    data = response.json()
    assert data["id"] == "dev-nuevo"
    assert data["device_uid"] == "00:11:22:33:44:55"
    assert data["nombre"] == "Nuevo Medidor"
    mocks["dispositivos"].registrar_dispositivo.assert_called_once()
    dto_creado = mocks["dispositivos"].registrar_dispositivo.call_args[0][0]
    assert dto_creado.device_uid == "00:11:22:33:44:55"
    assert dto_creado.nombre == "Nuevo Medidor"


def test_registrar_dispositivo_rol_invitado_403():
    client, mocks = _cliente(rol="invitado")

    payload = {
        "device_uid": "00:11:22:33:44:55",
        "nombre": "Nuevo Medidor",
    }
    response = client.post("/api/v1/dispositivos", json=payload)

    assert response.status_code == 403
    mocks["dispositivos"].registrar_dispositivo.assert_not_called()


def test_registrar_dispositivo_rol_invitado_global_403():
    client, mocks = _cliente(rol="invitado_global")

    payload = {
        "device_uid": "00:11:22:33:44:55",
        "nombre": "Nuevo Medidor",
    }
    response = client.post("/api/v1/dispositivos", json=payload)

    assert response.status_code == 403
    mocks["dispositivos"].registrar_dispositivo.assert_not_called()


def test_registrar_dispositivo_payload_invalido_422():
    client, _ = _cliente(rol="admin")

    # Falta el campo requerido device_uid
    payload = {
        "nombre": "Medidor Incompleto",
    }
    response = client.post("/api/v1/dispositivos", json=payload)

    assert response.status_code == 422


def test_registrar_dispositivo_limite_excedido_422():
    client, mocks = _cliente(rol="admin")
    mocks["dispositivos"].registrar_dispositivo.side_effect = LimiteDispositivosExcedidoError(
        "La organización alcanzó el límite de dispositivos."
    )

    payload = {
        "device_uid": "00:11:22:33:44:55",
        "nombre": "Medidor Excedente",
    }
    response = client.post("/api/v1/dispositivos", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"] == "La organización alcanzó el límite de dispositivos."


def test_registrar_dispositivo_error_inesperado_500():
    client, mocks = _cliente(rol="admin")
    mocks["dispositivos"].registrar_dispositivo.side_effect = RuntimeError("Error interno al registrar")

    payload = {
        "device_uid": "00:11:22:33:44:55",
    }
    response = client.post("/api/v1/dispositivos", json=payload)

    assert response.status_code == 500


# ==============================================================================
# 4. ACTUALIZAR DISPOSITIVO (PUT Y PATCH /api/v1/dispositivos/{device_id})
# ==============================================================================


def test_actualizar_dispositivo_put_exitoso():
    client, mocks = _cliente(rol="admin")
    mocks["dispositivos"].actualizar_dispositivo_de_organizacion.return_value = _dispositivo_dto(
        id="dev-1", nombre="Nombre Modificado PUT"
    )

    payload = {
        "nombre": "Nombre Modificado PUT",
        "ubicacion_tag": "Línea 2",
        "esta_activo": True,
    }
    response = client.put("/api/v1/dispositivos/dev-1", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["nombre"] == "Nombre Modificado PUT"
    mocks["dispositivos"].actualizar_dispositivo_de_organizacion.assert_called_once()
    device_id_llamado, dto_llamado = mocks["dispositivos"].actualizar_dispositivo_de_organizacion.call_args[0]
    assert device_id_llamado == "dev-1"
    assert dto_llamado.nombre == "Nombre Modificado PUT"


def test_actualizar_dispositivo_put_rol_invitado_403():
    client, mocks = _cliente(rol="invitado")

    response = client.put("/api/v1/dispositivos/dev-1", json={"nombre": "Nuevo"})

    assert response.status_code == 403
    mocks["dispositivos"].actualizar_dispositivo_de_organizacion.assert_not_called()


def test_actualizar_dispositivo_put_no_encontrado_404():
    client, mocks = _cliente(rol="admin")
    mocks["dispositivos"].actualizar_dispositivo_de_organizacion.side_effect = DispositivoNoEncontradoError(
        "Dispositivo 'dev-404' no encontrado."
    )

    response = client.put("/api/v1/dispositivos/dev-404", json={"nombre": "Nuevo"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Dispositivo 'dev-404' no encontrado."


def test_actualizar_dispositivo_put_limite_excedido_422():
    client, mocks = _cliente(rol="admin")
    mocks["dispositivos"].actualizar_dispositivo_de_organizacion.side_effect = LimiteDispositivosExcedidoError(
        "Cupo máximo alcanzado al cambiar de planta."
    )

    response = client.put("/api/v1/dispositivos/dev-1", json={"planta_id": "otra-planta"})

    assert response.status_code == 422
    assert response.json()["detail"] == "Cupo máximo alcanzado al cambiar de planta."


def test_actualizar_dispositivo_put_error_inesperado_500():
    client, mocks = _cliente(rol="admin")
    mocks["dispositivos"].actualizar_dispositivo_de_organizacion.side_effect = RuntimeError("Falla no controlada")

    response = client.put("/api/v1/dispositivos/dev-1", json={"nombre": "Nuevo"})

    assert response.status_code == 500


def test_actualizar_dispositivo_patch_exitoso():
    client, mocks = _cliente(rol="admin")
    mocks["dispositivos"].actualizar_dispositivo_de_organizacion.return_value = _dispositivo_dto(
        id="dev-1", esta_activo=False
    )

    payload = {"esta_activo": False}
    response = client.patch("/api/v1/dispositivos/dev-1", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["esta_activo"] is False
    mocks["dispositivos"].actualizar_dispositivo_de_organizacion.assert_called_once()
    device_id_llamado, dto_llamado = mocks["dispositivos"].actualizar_dispositivo_de_organizacion.call_args[0]
    assert device_id_llamado == "dev-1"
    assert dto_llamado.esta_activo is False


def test_actualizar_dispositivo_patch_rol_invitado_403():
    client, mocks = _cliente(rol="invitado")

    response = client.patch("/api/v1/dispositivos/dev-1", json={"esta_activo": False})

    assert response.status_code == 403
    mocks["dispositivos"].actualizar_dispositivo_de_organizacion.assert_not_called()


def test_actualizar_dispositivo_patch_no_encontrado_404():
    client, mocks = _cliente(rol="admin")
    mocks["dispositivos"].actualizar_dispositivo_de_organizacion.side_effect = DispositivoNoEncontradoError(
        "Dispositivo no encontrado."
    )

    response = client.patch("/api/v1/dispositivos/dev-999", json={"esta_activo": False})

    assert response.status_code == 404
    assert response.json()["detail"] == "Dispositivo no encontrado."


# ==============================================================================
# 5. ACTIVAR MODO REALTIME (POST /api/v1/dispositivos/{device_id}/realtime)
# ==============================================================================


@patch("src.infrastructure.fastapi.routes.dispositivos_router.get_mqtt_listener")
def test_activar_realtime_modo_exitoso_default_segundos(mock_get_listener):
    client, mocks = _cliente()
    mocks["dispositivos"].obtener_dispositivo_de_organizacion.return_value = _dispositivo_dto(
        id="dev-1", device_uid="00:11:22:33:44:55"
    )

    mock_listener = MagicMock()
    mock_listener.activar_tiempo_real_dispositivo.return_value = True
    mock_get_listener.return_value = mock_listener

    response = client.post("/api/v1/dispositivos/dev-1/realtime")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["device_id"] == "dev-1"
    assert data["device_uid"] == "00:11:22:33:44:55"
    assert data["tiempo_real_activado"] is True
    assert data["segundos"] == 120
    mocks["dispositivos"].obtener_dispositivo_de_organizacion.assert_called_once_with("dev-1", "org-1")
    mock_listener.activar_tiempo_real_dispositivo.assert_called_once_with("00:11:22:33:44:55", segundos=120)


@patch("src.infrastructure.fastapi.routes.dispositivos_router.get_mqtt_listener")
def test_activar_realtime_con_segundos_personalizado(mock_get_listener):
    client, mocks = _cliente()
    mocks["dispositivos"].obtener_dispositivo_de_organizacion.return_value = _dispositivo_dto(
        id="dev-1", device_uid="00:11:22:33:44:55"
    )

    mock_listener = MagicMock()
    mock_listener.activar_tiempo_real_dispositivo.return_value = True
    mock_get_listener.return_value = mock_listener

    response = client.post("/api/v1/dispositivos/dev-1/realtime?segundos=300")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["segundos"] == 300
    assert data["tiempo_real_activado"] is True
    mock_listener.activar_tiempo_real_dispositivo.assert_called_once_with("00:11:22:33:44:55", segundos=300)


@patch("src.infrastructure.fastapi.routes.dispositivos_router.get_mqtt_listener")
def test_activar_realtime_listener_none_mqtt_offline(mock_get_listener):
    client, mocks = _cliente()
    mocks["dispositivos"].obtener_dispositivo_de_organizacion.return_value = _dispositivo_dto(
        id="dev-1", device_uid="00:11:22:33:44:55"
    )
    mock_get_listener.return_value = None

    response = client.post("/api/v1/dispositivos/dev-1/realtime")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "mqtt_offline"
    assert data["device_id"] == "dev-1"
    assert data["device_uid"] == "00:11:22:33:44:55"
    assert data["tiempo_real_activado"] is False
    assert data["segundos"] == 120


@patch("src.infrastructure.fastapi.routes.dispositivos_router.get_mqtt_listener")
def test_activar_realtime_listener_envio_fallido(mock_get_listener):
    client, mocks = _cliente()
    mocks["dispositivos"].obtener_dispositivo_de_organizacion.return_value = _dispositivo_dto(
        id="dev-1", device_uid="00:11:22:33:44:55"
    )

    mock_listener = MagicMock()
    mock_listener.activar_tiempo_real_dispositivo.return_value = False
    mock_get_listener.return_value = mock_listener

    response = client.post("/api/v1/dispositivos/dev-1/realtime")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "mqtt_offline"
    assert data["tiempo_real_activado"] is False


def test_activar_realtime_segundos_menor_que_minimo_422():
    client, _ = _cliente()

    # Query param segundos ge=10
    response = client.post("/api/v1/dispositivos/dev-1/realtime?segundos=5")

    assert response.status_code == 422


def test_activar_realtime_segundos_mayor_que_maximo_422():
    client, _ = _cliente()

    # Query param segundos le=600
    response = client.post("/api/v1/dispositivos/dev-1/realtime?segundos=601")

    assert response.status_code == 422


def test_activar_realtime_dispositivo_no_encontrado_404():
    client, mocks = _cliente()
    mocks["dispositivos"].obtener_dispositivo_de_organizacion.side_effect = DispositivoNoEncontradoError(
        "Dispositivo no encontrado."
    )

    response = client.post("/api/v1/dispositivos/dev-inexistente/realtime")

    assert response.status_code == 404
    assert response.json()["detail"] == "Dispositivo no encontrado."


def test_activar_realtime_error_inesperado_500():
    client, mocks = _cliente()
    mocks["dispositivos"].obtener_dispositivo_de_organizacion.side_effect = RuntimeError("Fallo inesperado")

    response = client.post("/api/v1/dispositivos/dev-1/realtime")

    assert response.status_code == 500


def test_update_dto_acepta_categoria_tarifaria_libre_de_la_distribuidora():
    """categoria_tarifaria es string libre según la distribuidora (T3-MT, nomenclatura EDELAP T5M12)."""
    from src.application.dtos.dispositivo_dto import DispositivoUpdateDTO

    for categoria in ("T1-R", "T2", "T3-BT", "T3-MT", "T5M12"):
        assert DispositivoUpdateDTO(categoria_tarifaria=categoria).categoria_tarifaria == categoria
