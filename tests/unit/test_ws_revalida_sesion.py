"""tests/unit/test_ws_revalida_sesion.py — /ws/live revalida la sesión en cada latido (Issue #141).

Antes, el WebSocket validaba el token solo al conectar: una cuenta dada de baja, una sesión revocada o un token
vencido seguían recibiendo eventos hasta cerrar la conexión. Ahora el latido (cada 25 s) vuelve a chequear la
sesión y cierra la conexión si ya no es vigente.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.fastapi import server
from src.infrastructure.fastapi.server import (
    WS_CLOSE_TOKEN_INVALIDO,
    ConnectedClient,
    _ws_heartbeat_loop,
)
from src.infrastructure.fastapi.vigencia_sesion import sesion_vigente

ahora_ts = int(datetime.now(timezone.utc).timestamp())


def _usuario(esta_activo: bool = True, revocadas_antes_de: datetime | None = None) -> MagicMock:
    usuario = MagicMock()
    usuario.esta_activo = esta_activo
    usuario.sesiones_revocadas_antes_de = revocadas_antes_de
    return usuario


def _repo(usuario: MagicMock | None) -> MagicMock:
    repo = MagicMock()
    repo.obtener_por_id.return_value = usuario
    return repo


def _revocacion(revocado: bool = False) -> MagicMock:
    servicio = MagicMock()
    servicio.esta_revocado.return_value = revocado
    return servicio


def _claims(iat: int | None = None) -> dict:
    return {"sub": "u-1", "rol": "operador", "org": "org-1", "iat": iat or ahora_ts - 60}


class TestSesionVigente:
    def test_usuario_activo_y_sesion_no_revocada_es_vigente(self):
        assert sesion_vigente(_claims(), _repo(_usuario()), _revocacion()) is True

    def test_cuenta_dada_de_baja_no_es_vigente(self):
        assert sesion_vigente(_claims(), _repo(_usuario(esta_activo=False)), _revocacion()) is False

    def test_token_revocado_en_memoria_no_es_vigente(self):
        assert sesion_vigente(_claims(), _repo(_usuario()), _revocacion(revocado=True)) is False

    def test_sesion_revocada_por_cambio_de_contrasena_no_es_vigente(self):
        revocadas_desde = datetime.now(timezone.utc) + timedelta(minutes=5)
        usuario = _usuario(revocadas_antes_de=revocadas_desde)
        assert sesion_vigente(_claims(), _repo(usuario), _revocacion()) is False

    def test_usuario_inexistente_en_base_solo_depende_de_la_revocacion(self):
        assert sesion_vigente(_claims(), _repo(None), _revocacion()) is True


class TestRevalidacionEnLatido:
    def test_latido_cierra_la_conexion_de_una_sesion_no_vigente(self):
        server.active_websockets.clear()
        websocket = AsyncMock()
        cliente = ConnectedClient(
            websocket=websocket,
            organizacion_id="org-1",
            es_superadmin=False,
            plantas_permitidas=None,
            claims=_claims(),
        )
        server.active_websockets.append(cliente)
        esperas = iter([None, asyncio.CancelledError()])

        async def _sleep(_s: float) -> None:
            resultado = next(esperas)
            if resultado is not None:
                raise resultado

        try:
            with (
                patch("src.infrastructure.fastapi.server.asyncio.sleep", side_effect=_sleep),
                patch("src.infrastructure.fastapi.server.get_mqtt_listener", return_value=None),
                patch("src.infrastructure.fastapi.server.sesion_ws_vigente", return_value=False),
            ):
                asyncio.run(_ws_heartbeat_loop(MagicMock()))
            assert cliente not in server.active_websockets
            websocket.close.assert_awaited_once_with(code=WS_CLOSE_TOKEN_INVALIDO, reason="sesion_no_vigente")
        finally:
            server.active_websockets.clear()

    def test_latido_no_cierra_una_sesion_vigente(self):
        server.active_websockets.clear()
        websocket = AsyncMock()
        cliente = ConnectedClient(
            websocket=websocket,
            organizacion_id="org-1",
            es_superadmin=False,
            plantas_permitidas=None,
            claims=_claims(),
        )
        server.active_websockets.append(cliente)
        esperas = iter([None, asyncio.CancelledError()])

        async def _sleep(_s: float) -> None:
            resultado = next(esperas)
            if resultado is not None:
                raise resultado

        try:
            with (
                patch("src.infrastructure.fastapi.server.asyncio.sleep", side_effect=_sleep),
                patch("src.infrastructure.fastapi.server.get_mqtt_listener", return_value=None),
                patch("src.infrastructure.fastapi.server.sesion_ws_vigente", return_value=True),
            ):
                asyncio.run(_ws_heartbeat_loop(MagicMock()))
            assert cliente in server.active_websockets
            websocket.close.assert_not_awaited()
        finally:
            server.active_websockets.clear()

    def test_cliente_sin_claims_no_se_revalida(self):
        """Con AUTH_REQUIRED apagado el cliente no tiene token: no hay sesión que revalidar."""
        server.active_websockets.clear()
        websocket = AsyncMock()
        cliente = ConnectedClient(websocket=websocket, organizacion_id=None, es_superadmin=True)
        server.active_websockets.append(cliente)
        esperas = iter([None, asyncio.CancelledError()])

        async def _sleep(_s: float) -> None:
            resultado = next(esperas)
            if resultado is not None:
                raise resultado

        try:
            with (
                patch("src.infrastructure.fastapi.server.asyncio.sleep", side_effect=_sleep),
                patch("src.infrastructure.fastapi.server.get_mqtt_listener", return_value=None),
                patch("src.infrastructure.fastapi.server.sesion_ws_vigente") as vigente,
            ):
                asyncio.run(_ws_heartbeat_loop(MagicMock()))
            vigente.assert_not_called()
            assert cliente in server.active_websockets
        finally:
            server.active_websockets.clear()
