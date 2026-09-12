"""tests/unit/test_ws_auth_rechazo.py — Pruebas del manejo de rechazo de autenticación en /ws/live (specs/ws-auth-rechazo.md)."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.infrastructure.auth.jwt_token_service import JwtTokenService
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.settings.config import Settings


def _app_con_auth() -> FastAPI:
    settings = Settings(
        _env_file=None,
        AUTH_REQUIRED=True,
        DEBUG=True,
        API_SECRET_KEY="s3cr3t0",
        APP_ENV="test",
    )
    return create_app(settings)


def _token_valido() -> str:
    service = JwtTokenService("s3cr3t0")
    return service.generar(
        "usuario-1",
        "operador@planta.local",
        datetime.now(timezone.utc) + timedelta(minutes=30),
    )


def test_ws_cierra_con_4401_si_token_invalido():
    client = TestClient(_app_con_auth())

    with client.websocket_connect("/ws/live") as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_text()

    assert exc.value.code == 4401
    assert exc.value.reason == "token_invalido"


def test_ws_acepta_token_valido_y_permanece_abierto():
    client = TestClient(_app_con_auth())
    client.cookies.set("datamaq_token", _token_valido())

    with client.websocket_connect("/ws/live") as ws:
        ws.send_text("ping")
        # El loop del servidor recibió "ping" y sigue abierto: sin WebSocketDisconnect.
