"""tests/unit/test_solo_lectura_bloquea_escrituras.py — El rol solo_lectura no escribe en ninguna ruta (#99, parche).

Usa tokens firmados con el mismo servicio que el backend. Las rutas de prueba imitan las del hueco: una POST sin
guard de rol (realtime) y una POST autenticada (logout-todas).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.infrastructure.auth.jwt_token_service import JwtTokenService
from src.infrastructure.fastapi.middleware import registrar_guard_solo_lectura

SECRETO = "clave-de-prueba-larga-0123456789abcdef"


def _token(rol: str) -> str:
    expira = datetime.now(timezone.utc) + timedelta(hours=1)
    return JwtTokenService(SECRETO).generar("usuario-1", "usuario", expira, rol=rol, organizacion_id="org-1")


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/v1/telemetria/x")
    def lectura():
        return {"ok": True}

    @app.post("/api/v1/dispositivos/{device_id}/realtime")
    def realtime(device_id: str):
        return {"ok": True}

    @app.post("/api/v1/auth/logout-todas")
    def logout_todas():
        return {"ok": True}

    @app.post("/api/v1/auth/logout")
    def logout():
        return {"ok": True}

    @app.post("/api/v1/auth/login")
    def login():
        return {"ok": True}

    @app.post("/api/v1/cualquiera")
    def cualquiera():
        return {"ok": True}

    ajustes = MagicMock(
        API_SOLO_LECTURA=False,
        API_SOLO_LECTURA_EXCEPCIONES="",
        DB_NAME="datamaq_telemetry",
        API_SECRET_KEY=SECRETO,
        API_SECRET_KEY_ANTERIOR="",
        AUTH_COOKIE_NOMBRE="datamaq_token",
    )
    registrar_guard_solo_lectura(app, ajustes)
    return app


@pytest.fixture
def cliente():
    return TestClient(_app())


def _bearer(rol: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(rol)}"}


def test_solo_lectura_recibe_403_en_realtime(cliente):
    respuesta = cliente.post("/api/v1/dispositivos/abc/realtime", headers=_bearer("solo_lectura"))
    assert respuesta.status_code == 403


def test_solo_lectura_recibe_403_en_logout_todas(cliente):
    respuesta = cliente.post("/api/v1/auth/logout-todas", headers=_bearer("solo_lectura"))
    assert respuesta.status_code == 403


def test_solo_lectura_recibe_403_en_un_post_cualquiera_por_cookie(cliente):
    cliente.cookies.set("datamaq_token", _token("solo_lectura"))
    assert cliente.post("/api/v1/cualquiera").status_code == 403


def test_solo_lectura_recibe_200_en_un_get_autorizado(cliente):
    assert cliente.get("/api/v1/telemetria/x", headers=_bearer("solo_lectura")).status_code == 200


def test_solo_lectura_puede_entrar_y_salir_de_su_propia_sesion(cliente):
    assert cliente.post("/api/v1/auth/login", headers=_bearer("solo_lectura")).status_code == 200
    assert cliente.post("/api/v1/auth/logout", headers=_bearer("solo_lectura")).status_code == 200


@pytest.mark.parametrize("rol", ["admin", "operador", "superadmin", "ingeniero"])
def test_los_otros_roles_no_cambian(cliente, rol):
    assert cliente.post("/api/v1/cualquiera", headers=_bearer(rol)).status_code == 200


def test_sin_token_no_bloquea_y_deja_la_decision_a_la_ruta(cliente):
    # Sin credenciales el middleware no decide: la ruta responde como hoy.
    assert cliente.post("/api/v1/cualquiera").status_code == 200


def test_token_invalido_no_bloquea(cliente):
    respuesta = cliente.post("/api/v1/cualquiera", headers={"Authorization": "Bearer no-es-un-jwt"})
    assert respuesta.status_code == 200
