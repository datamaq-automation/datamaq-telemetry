"""tests/unit/test_realtime_command.py."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from src.infrastructure.fastapi import server
from src.infrastructure.fastapi.dependencies import registrar_mqtt_listener
from src.infrastructure.fastapi.renovacion_tiempo_real import INTERVALO_RENOVACION_S, marca_renovacion
from src.infrastructure.fastapi.server import (
    ConnectedClient,
    _registrar_cliente_ws,
    _renovar_modo_tiempo_real_medidores,
    _ws_heartbeat_loop,
    create_app,
)
from src.infrastructure.paho_mqtt.mqtt_listener import MQTTListener


def test_activar_tiempo_real_dispositivo_publica_comando():
    listener = MQTTListener.__new__(MQTTListener)
    listener._esta_conectado = True
    listener.client = MagicMock()
    listener.settings = MagicMock()

    mock_info = MagicMock()
    listener.client.publish.return_value = mock_info

    resultado = listener.activar_tiempo_real_dispositivo("D48C49F03564", segundos=90)
    assert resultado is True
    listener.client.publish.assert_called_once()
    args, _ = listener.client.publish.call_args
    topico, payload_str = args
    assert topico == "m/wifi/D48C49F03564/conf/com"
    assert '"set": "realtime_sync_mode"' in payload_str
    assert '"time_s": 90' in payload_str


def test_endpoint_activar_tiempo_real():
    mock_listener = MagicMock()
    mock_listener.esta_conectado.return_value = True
    mock_listener.activar_tiempo_real_dispositivo.return_value = True
    registrar_mqtt_listener(mock_listener)

    from src.infrastructure.fastapi.dependencies import (
        get_dispositivos_use_case,
        get_usuario_actual,
    )

    app = create_app()
    mock_uc = MagicMock()
    mock_disp = MagicMock()
    mock_disp.id = "disp-1"
    mock_disp.device_uid = "D48C49F03564"
    mock_uc.obtener_dispositivo.return_value = mock_disp

    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "user-test", "rol": "operador"}
    app.dependency_overrides[get_dispositivos_use_case] = lambda: mock_uc

    client = TestClient(app)
    resp = client.post("/api/v1/dispositivos/disp-1/realtime?segundos=120")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["tiempo_real_activado"] is True
    assert data["device_uid"] == "D48C49F03564"


def test_renovar_modo_tiempo_real_medidores_itera_dispositivos():
    mock_listener = MagicMock()
    mock_listener.esta_conectado.return_value = True

    mock_db = MagicMock()
    mock_repo = MagicMock()
    mock_disp = MagicMock()
    mock_disp.device_uid.valor = "AABBCCDDEEFF"
    mock_disp.visto_por_ultima_vez = datetime.now(timezone.utc)
    mock_repo.listar.return_value = [mock_disp]

    with (
        patch("src.infrastructure.fastapi.renovacion_tiempo_real.get_session_factory", return_value=lambda: mock_db),
        patch("src.infrastructure.fastapi.renovacion_tiempo_real.MySQLDispositivosRepository", return_value=mock_repo),
    ):
        _renovar_modo_tiempo_real_medidores(mock_listener, [_cliente(es_superadmin=True)])

        mock_listener.activar_tiempo_real_dispositivo.assert_called_once_with("AABBCCDDEEFF", segundos=120)
        mock_repo.listar.assert_called_once_with()


def test_renovar_con_cliente_de_una_organizacion_lista_solo_esa_organizacion():
    mock_repo = MagicMock()
    mock_repo.listar.return_value = []
    with (
        patch(
            "src.infrastructure.fastapi.renovacion_tiempo_real.get_session_factory", return_value=lambda: MagicMock()
        ),
        patch("src.infrastructure.fastapi.renovacion_tiempo_real.MySQLDispositivosRepository", return_value=mock_repo),
    ):
        _renovar_modo_tiempo_real_medidores(MagicMock(), [_cliente(org="org-a")])
    mock_repo.listar.assert_called_once_with(organizacion_id="org-a")


def test_renovar_sin_alcance_no_abre_sesion():
    with patch("src.infrastructure.fastapi.renovacion_tiempo_real.get_session_factory") as factory:
        _renovar_modo_tiempo_real_medidores(MagicMock(), [_cliente(org=None)])
    factory.assert_not_called()


@pytest.fixture(autouse=True)
def _marca_limpia():
    """La marca es estado de módulo: cada test arranca sin renovación previa."""
    marca_renovacion.ultima = 0.0
    yield
    marca_renovacion.ultima = 0.0


def _cliente(org: str | None = None, es_superadmin: bool = False) -> ConnectedClient:
    return ConnectedClient(websocket=MagicMock(), organizacion_id=org, es_superadmin=es_superadmin)


@pytest.fixture
def renovaciones():
    """Clientes con los que se pidió renovar al conectar uno nuevo; aísla `active_websockets`."""
    llamadas: list[list[ConnectedClient]] = []
    listener = MagicMock()
    listener.esta_conectado.return_value = True
    server.active_websockets.clear()
    with (
        patch("src.infrastructure.fastapi.server.get_mqtt_listener", return_value=listener),
        patch(
            "src.infrastructure.fastapi.server._renovar_modo_tiempo_real_medidores",
            side_effect=lambda _l, clientes: llamadas.append(clientes),
        ),
    ):
        yield llamadas
    server.active_websockets.clear()


def test_primer_cliente_renueva_su_alcance(renovaciones):
    cliente = _cliente(org="org-a")
    _registrar_cliente_ws(cliente, "h")
    assert renovaciones == [[cliente]]


def test_cliente_de_una_organizacion_ya_cubierta_no_renueva(renovaciones):
    _registrar_cliente_ws(_cliente(org="org-a"), "h")
    _registrar_cliente_ws(_cliente(org="org-a"), "h")
    assert len(renovaciones) == 1


def test_cliente_de_otra_organizacion_renueva_sin_esperar_al_heartbeat(renovaciones):
    _registrar_cliente_ws(_cliente(org="org-a"), "h")
    nuevo = _cliente(org="org-b")
    _registrar_cliente_ws(nuevo, "h")
    assert renovaciones[-1] == [nuevo]
    assert len(renovaciones) == 2


def test_con_superadmin_conectado_otro_cliente_no_renueva(renovaciones):
    _registrar_cliente_ws(_cliente(es_superadmin=True), "h")
    _registrar_cliente_ws(_cliente(org="org-b"), "h")
    assert len(renovaciones) == 1


def test_superadmin_que_llega_despues_renueva(renovaciones):
    _registrar_cliente_ws(_cliente(org="org-a"), "h")
    superadmin = _cliente(es_superadmin=True)
    _registrar_cliente_ws(superadmin, "h")
    assert renovaciones[-1] == [superadmin]


def test_heartbeat_loguea_el_error_en_vez_de_tragarlo():
    server.active_websockets.clear()
    cliente = ConnectedClient(websocket=AsyncMock(), organizacion_id="org-a", es_superadmin=False)
    server.active_websockets.append(cliente)
    esperas = iter([None, asyncio.CancelledError()])

    async def _sleep(_s: float) -> None:
        resultado = next(esperas)
        if resultado is not None:
            raise resultado

    try:
        with (
            patch("src.infrastructure.fastapi.server.asyncio.sleep", side_effect=_sleep),
            patch("src.infrastructure.fastapi.server.get_mqtt_listener", side_effect=RuntimeError("broker caido")),
            patch("src.infrastructure.fastapi.server.logger") as logger,
        ):
            asyncio.run(_ws_heartbeat_loop())
    finally:
        server.active_websockets.clear()
    logger.warning.assert_called_once_with("ws_heartbeat_fallido", error="broker caido")


def _un_tick_de_heartbeat() -> None:
    """Corre una vuelta de `_ws_heartbeat_loop` sin esperar los 25 s."""
    esperas = iter([None, asyncio.CancelledError()])

    async def _sleep(_s: float) -> None:
        resultado = next(esperas)
        if resultado is not None:
            raise resultado

    with patch("src.infrastructure.fastapi.server.asyncio.sleep", side_effect=_sleep):
        asyncio.run(_ws_heartbeat_loop())


def _con_websocket_async(cliente: ConnectedClient) -> ConnectedClient:
    cliente.websocket = AsyncMock()
    return cliente


def test_primer_tick_del_heartbeat_no_repite_la_renovacion_de_la_conexion(renovaciones):
    """#15: al conectarse se veían dos realtime_mode_auto_renovado separados por 1,4 s."""
    _registrar_cliente_ws(_con_websocket_async(_cliente(org="org-a")), "h")
    _un_tick_de_heartbeat()
    assert len(renovaciones) == 1


def test_heartbeat_renueva_cuando_vence_la_marca(renovaciones):
    _registrar_cliente_ws(_con_websocket_async(_cliente(org="org-a")), "h")
    marca_renovacion.ultima -= INTERVALO_RENOVACION_S
    _un_tick_de_heartbeat()
    assert len(renovaciones) == 2


def test_cliente_de_otra_organizacion_no_corre_la_marca_de_las_ya_conectadas(renovaciones):
    """Correrla dejaría a org-a sin renovar más de 120 s: el medidor volvería a 5 min."""
    _registrar_cliente_ws(_con_websocket_async(_cliente(org="org-a")), "h")
    marca_previa = marca_renovacion.ultima
    _registrar_cliente_ws(_con_websocket_async(_cliente(org="org-b")), "h")
    assert len(renovaciones) == 2
    assert marca_renovacion.ultima == marca_previa


def test_superadmin_que_llega_despues_corre_la_marca(renovaciones):
    _registrar_cliente_ws(_con_websocket_async(_cliente(org="org-a")), "h")
    marca_renovacion.ultima = 0.0
    _registrar_cliente_ws(_con_websocket_async(_cliente(es_superadmin=True)), "h")
    assert marca_renovacion.ultima > 0.0
