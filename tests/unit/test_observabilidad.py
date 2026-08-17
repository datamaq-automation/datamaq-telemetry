"""Observabilidad de errores HTTP: request_id, logging de errores y mapeo consistente."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from src.domain.auth.exceptions import CredencialesInvalidasError, DemasiadosIntentosError
from src.infrastructure.fastapi.error_handler import manejar_error_http
from src.infrastructure.fastapi.middleware import RequestIdMiddleware


def _app_con_middleware() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/boom")
    def boom():
        try:
            raise Exception("detalle-interno")
        except Exception as e:
            manejar_error_http(e)

    @app.get("/login-invalido")
    def login_invalido():
        try:
            raise CredencialesInvalidasError("Credenciales inválidas.")
        except Exception as e:
            manejar_error_http(e)

    return app


# E1 — 500 trazable: header X-Request-ID + log error_interno con request_id
def test_error_interno_incluye_request_id_en_header_y_log():
    client = TestClient(_app_con_middleware(), raise_server_exceptions=False)
    with capture_logs() as logs:
        respuesta = client.get("/boom")

    assert respuesta.status_code == 500
    assert "X-Request-ID" in respuesta.headers
    request_id = respuesta.headers["X-Request-ID"]

    errores = [e for e in logs if e.get("event") == "error_interno"]
    assert errores, "No se registró el evento error_interno"
    assert errores[0]["request_id"] == request_id


# E2 — dos requests con error producen request_ids distintos
def test_request_id_unico_por_request():
    client = TestClient(_app_con_middleware(), raise_server_exceptions=False)
    primero = client.get("/boom").headers["X-Request-ID"]
    segundo = client.get("/boom").headers["X-Request-ID"]
    assert primero != segundo


# E3 — error de negocio: 401 + warning sin stack ni contrasena
def test_error_negocio_loguea_warning_sin_exc_info_ni_secretos():
    client = TestClient(_app_con_middleware(), raise_server_exceptions=False)
    with capture_logs() as logs:
        respuesta = client.get("/login-invalido")

    assert respuesta.status_code == 401
    negocios = [e for e in logs if e.get("event") == "error_negocio"]
    assert negocios, "No se registró el evento error_negocio"
    assert "exc_info" not in negocios[0]
    assert "exception" not in negocios[0]
    assert "contrasena" not in negocios[0]


# E4 — mapeo de errores independiente del modo
def test_mapeo_errores_independiente_del_modo():
    import pytest as _pytest
    from fastapi import HTTPException

    with _pytest.raises(HTTPException) as e_credenciales:
        manejar_error_http(CredencialesInvalidasError("Credenciales inválidas."))
    assert e_credenciales.value.status_code == 401

    with _pytest.raises(HTTPException) as e_intentos:
        manejar_error_http(DemasiadosIntentosError("Demasiados intentos."))
    assert e_intentos.value.status_code == 429

    with _pytest.raises(HTTPException) as e_generico:
        manejar_error_http(Exception("inesperado"))
    assert e_generico.value.status_code == 500
