"""Observabilidad de errores HTTP: request_id, logging de errores y mapeo consistente."""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException
from structlog.testing import capture_logs

from src.domain.auth.exceptions import CredencialesInvalidasError, DemasiadosIntentosError
from src.domain.telemetria.exceptions import DispositivoNoEncontradoError
from src.infrastructure.fastapi.error_handler import manejar_404, manejar_error_http
from src.infrastructure.fastapi.middleware import RequestIdMiddleware


def _app_con_middleware() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(StarletteHTTPException, manejar_404)

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

    @app.get("/recurso-no-encontrado")
    def recurso_no_encontrado():
        try:
            raise DispositivoNoEncontradoError("Dispositivo 'xyz' no encontrado.")
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


# E5 — error de negocio con usuario: incluye la clave usuario y no contrasena
def test_error_negocio_con_usuario():
    with capture_logs() as logs:
        with pytest.raises(HTTPException) as e:
            manejar_error_http(CredencialesInvalidasError("Credenciales inválidas.", usuario="operador"))

    assert e.value.status_code == 401
    negocios = [ev for ev in logs if ev.get("event") == "error_negocio"]
    assert negocios, "No se registró el evento error_negocio"
    assert negocios[0]["usuario"] == "operador"
    assert "contrasena" not in negocios[0]


# E6 — error de negocio sin usuario: la clave usuario no se emite
def test_error_negocio_sin_usuario():
    with capture_logs() as logs:
        with pytest.raises(HTTPException):
            manejar_error_http(CredencialesInvalidasError("Credenciales inválidas."))

    negocios = [ev for ev in logs if ev.get("event") == "error_negocio"]
    assert negocios, "No se registró el evento error_negocio"
    assert "usuario" not in negocios[0]


# E7 — DemasiadosIntentosError con usuario: 429 + usuario en log
def test_demasiados_intentos_con_usuario():
    with capture_logs() as logs:
        with pytest.raises(HTTPException) as e:
            manejar_error_http(DemasiadosIntentosError("Demasiados intentos.", usuario="operador", retry_after_seg=37))

    assert e.value.status_code == 429
    assert e.value.headers["Retry-After"] == "37"
    negocios = [ev for ev in logs if ev.get("event") == "error_negocio"]
    assert negocios, "No se registró el evento error_negocio"
    assert negocios[0]["usuario"] == "operador"


# E9 — ruta inexistente: 404 + log ruta_no_encontrada correlacionado
def test_ruta_inexistente_loguea_ruta_no_encontrada():
    client = TestClient(_app_con_middleware(), raise_server_exceptions=False)
    with capture_logs() as logs:
        respuesta = client.get("/ruta-inexistente")

    assert respuesta.status_code == 404
    request_id = respuesta.headers["X-Request-ID"]
    rutas = [ev for ev in logs if ev.get("event") == "ruta_no_encontrada"]
    assert rutas, "No se registró el evento ruta_no_encontrada"
    assert rutas[0]["metodo"] == "GET"
    assert rutas[0]["path"] == "/ruta-inexistente"
    assert rutas[0]["request_id"] == request_id


# E10 — 404 de negocio no duplica el log de ruta_no_encontrada
def test_404_negocio_no_loguea_ruta_no_encontrada():
    client = TestClient(_app_con_middleware(), raise_server_exceptions=False)
    with capture_logs() as logs:
        respuesta = client.get("/recurso-no-encontrado")

    assert respuesta.status_code == 404
    negocios = [ev for ev in logs if ev.get("event") == "error_negocio"]
    assert negocios, "Se esperaba el evento error_negocio"
    rutas = [ev for ev in logs if ev.get("event") == "ruta_no_encontrada"]
    assert not rutas, "No se debe loguear ruta_no_encontrada para un 404 de negocio"


# E11 — /favicon.ico responde 204 No Content sin error
def test_favicon_endpoint_retorna_204():
    from src.infrastructure.fastapi.routes.system_router import router as system_router

    app = FastAPI()
    app.include_router(system_router)
    client = TestClient(app)
    respuesta = client.get("/favicon.ico")
    assert respuesta.status_code == 204


# E12 — error de BD estructurado con orig y statement
def test_error_db_loguea_detalles_estructurados():
    class DBFakeError(Exception):
        orig = "(1054, \"Unknown column 'thd_v_r' in 'field list'\")"
        statement = "SELECT telemetry_instantaneous.thd_v_r FROM telemetry_instantaneous"

    with capture_logs() as logs:
        with pytest.raises(HTTPException) as exc_info:
            manejar_error_http(DBFakeError("Error en query"))

    assert exc_info.value.status_code == 500
    errores = [ev for ev in logs if ev.get("event") == "error_interno"]
    assert errores, "No se registró el evento error_interno"
    assert "Unknown column 'thd_v_r'" in errores[0].get("db_error", "")
    assert "telemetry_instantaneous" in errores[0].get("db_statement", "")
