"""tests/unit/test_observabilidad.py — Observabilidad de errores HTTP: request_id, logging de errores y mapeo consistente."""

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


# E10b — Sonda sospechosa (escaneo externo): 404 + log sonda_sospechosa sin ensuciar ruta_no_encontrada
@pytest.mark.parametrize(
    "ruta_sonda",
    [
        "/.env",
        "/api/v1/.env",
        "/docker/.env",
        "/lib/file-control.php",
        "/api/v1/node-load-method/customMCP",
        "/langflow/api",
        "/terraform.tfstate",
        "/compose.yaml",
        "/service_account.json",
        "/wp-admin/setup-config.php",
        "/proc/self/environ",
        "/z9x8c7v6b5-debug-trigger-api.datamaq.com.ar",
    ],
)
def test_sonda_sospechosa_loguea_sonda_y_no_ruta_no_encontrada(ruta_sonda: str):
    client = TestClient(_app_con_middleware(), raise_server_exceptions=False)
    with capture_logs() as logs:
        respuesta = client.get(ruta_sonda, headers={"X-Forwarded-For": "136.69.200.122, 10.0.0.1"})

    assert respuesta.status_code == 404
    sondas = [ev for ev in logs if ev.get("event") == "sonda_sospechosa"]
    assert sondas, f"No se registró el evento sonda_sospechosa para {ruta_sonda}"
    assert sondas[0]["path"] == ruta_sonda
    assert sondas[0]["metodo"] == "GET"
    assert sondas[0]["ip"] == "136.69.200.122"
    assert "request_id" in sondas[0]

    rutas_normales = [ev for ev in logs if ev.get("event") == "ruta_no_encontrada"]
    assert not rutas_normales, f"No se debió registrar ruta_no_encontrada para {ruta_sonda}"


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


# E13 — Sondas de salud: /health/live siempre 200, /health/ready valida BD y migraciones
def test_liveness_endpoint_retorna_200():
    from src.infrastructure.fastapi.routes.system_router import router as system_router

    app = FastAPI()
    app.include_router(system_router)
    client = TestClient(app)
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "alive"


def test_readiness_endpoint_retorna_200_cuando_ok(monkeypatch):
    from src.infrastructure.fastapi.routes import system_router as sys_mod
    from src.infrastructure.fastapi.routes.system_router import router as system_router

    monkeypatch.setattr(sys_mod, "verificar_conexion_db", lambda: True)
    monkeypatch.setattr(
        sys_mod, "verificar_estado_migraciones", lambda: {"sincronizado": True, "current_rev": "h1", "head_rev": "h1"}
    )

    app = FastAPI()
    app.include_router(system_router)
    client = TestClient(app)
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_readiness_endpoint_retorna_503_cuando_falla_migracion_o_db(monkeypatch):
    from src.infrastructure.fastapi.routes import system_router as sys_mod
    from src.infrastructure.fastapi.routes.system_router import router as system_router

    # Caso 1: DB caída
    monkeypatch.setattr(sys_mod, "verificar_conexion_db", lambda: False)
    monkeypatch.setattr(
        sys_mod, "verificar_estado_migraciones", lambda: {"sincronizado": True, "current_rev": "h1", "head_rev": "h1"}
    )

    app = FastAPI()
    app.include_router(system_router)
    client = TestClient(app)
    resp = client.get("/health/ready")
    assert resp.status_code == 503
    assert resp.json()["status"] == "not_ready"

    # Caso 2: Desfasaje de migración
    monkeypatch.setattr(sys_mod, "verificar_conexion_db", lambda: True)
    monkeypatch.setattr(
        sys_mod,
        "verificar_estado_migraciones",
        lambda: {"sincronizado": False, "current_rev": "rev_vieja", "head_rev": "rev_head"},
    )
    resp2 = client.get("/health/ready")
    assert resp2.status_code == 503
    assert resp2.json()["status"] == "not_ready"
