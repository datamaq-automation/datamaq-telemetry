"""tests/unit/test_roles_escritura_issue99.py — Issue #99.

Escrituras sobre datos de planta, dispositivos e integraciones exigen rol de escritura explícito.
Por ruta: un rol sin escritura (solo_lectura) recibe 403 con el detalle del guard; un rol operativo pasa.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.infrastructure.fastapi.dependencies import get_dispositivos_use_case, get_oauth_repository, get_usuario_actual
from src.infrastructure.fastapi.device_ownership import verificar_propiedad_dispositivo
from src.infrastructure.fastapi.server import create_app


def _cliente(rol: str) -> tuple[TestClient, MagicMock]:
    app = create_app()
    claims = {"sub": "u1", "rol": rol, "org": "org-1"}
    app.dependency_overrides[get_usuario_actual] = lambda: claims
    dispositivos = MagicMock()
    app.dependency_overrides[get_dispositivos_use_case] = lambda: dispositivos
    app.dependency_overrides[get_oauth_repository] = lambda: MagicMock()
    # Este archivo prueba el guard de rol (#99); la propiedad por planta tiene su batería (datamaq#126).
    app.dependency_overrides[verificar_propiedad_dispositivo] = lambda: None
    return TestClient(app), dispositivos


@patch("src.infrastructure.fastapi.routes.dispositivos_router.get_mqtt_listener", new=MagicMock())
def test_realtime_sin_rol_de_escritura_responde_403():
    client, dispositivos = _cliente("solo_lectura")

    respuesta = client.post("/api/v1/dispositivos/dev-1/realtime")

    assert respuesta.status_code == 403
    assert respuesta.json()["detail"] == "forbidden"
    dispositivos.obtener_dispositivo_de_organizacion.assert_not_called()


@patch("src.infrastructure.fastapi.routes.dispositivos_router.get_mqtt_listener")
def test_realtime_con_rol_operativo_pasa(mock_get_listener):
    client, dispositivos = _cliente("operador")
    dispositivos.obtener_dispositivo_de_organizacion.return_value = SimpleNamespace(
        id="dev-1", device_uid="00:11:22:33:44:55"
    )
    listener = MagicMock()
    listener.activar_tiempo_real_dispositivo.return_value = True
    mock_get_listener.return_value = listener

    respuesta = client.post("/api/v1/dispositivos/dev-1/realtime")

    assert respuesta.status_code == 200
    assert respuesta.json()["tiempo_real_activado"] is True


@patch("src.infrastructure.fastapi.routes.oauth_router.GestionarIntegracionesUsuarioUseCase")
def test_revocar_integracion_sin_rol_de_escritura_responde_403(mock_uc):
    client, _ = _cliente("solo_lectura")

    respuesta = client.delete("/api/v1/usuarios/integraciones/claude-ai")

    assert respuesta.status_code == 403
    assert respuesta.json()["detail"] == "forbidden"
    mock_uc.assert_not_called()


@patch("src.infrastructure.fastapi.routes.oauth_router.GestionarIntegracionesUsuarioUseCase")
def test_revocar_integracion_con_rol_operativo_pasa(mock_uc):
    client, _ = _cliente("operador")
    mock_uc.return_value.revocar_por_cliente.return_value = 1

    respuesta = client.delete("/api/v1/usuarios/integraciones/claude-ai")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"client_id": "claude-ai", "revocados": 1, "status": "ok"}
