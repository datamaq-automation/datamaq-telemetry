"""tests/unit/test_seguridad_rutas.py — Tests para rechazo de path traversal y rate limit 404."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from src.infrastructure.fastapi.middleware import RequestIdMiddleware
from src.infrastructure.fastapi.seguridad_rutas import (
    RateLimit404Middleware,
    RechazoPathInseguroMiddleware,
    contiene_secuencia_insegura,
)
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.settings.config import Settings


def test_contiene_secuencia_insegura_rutas_normales():
    assert contiene_secuencia_insegura("/api/v1/telemetria")[0] is False
    assert contiene_secuencia_insegura("/health")[0] is False
    assert contiene_secuencia_insegura("/api/plantas/1/unifilar")[0] is False


def test_contiene_secuencia_insegura_traversal_directo():
    inseguro, motivo = contiene_secuencia_insegura("/api/w/admins/jobs_u/get_log_file/../../../../proc/self/environ")
    assert inseguro is True
    assert "traversal" in motivo

    inseguro_semicolon, motivo_semicolon = contiene_secuencia_insegura("/api/..;/.env")
    assert inseguro_semicolon is True
    assert "traversal" in motivo_semicolon


def test_contiene_secuencia_insegura_traversal_encoded():
    inseguro, motivo = contiene_secuencia_insegura("/api/%2e%2e/bar", raw_path=b"/api/%2e%2e/bar")
    assert inseguro is True
    assert "traversal" in motivo

    inseguro_upper, motivo_upper = contiene_secuencia_insegura("/api/%2E%2E/bar", raw_path=b"/api/%2E%2E/bar")
    assert inseguro_upper is True
    assert "traversal" in motivo_upper

    inseguro_doble, motivo_doble = contiene_secuencia_insegura("/api/%252e%252e/bar", raw_path=b"/api/%252e%252e/bar")
    assert inseguro_doble is True
    assert "traversal" in motivo_doble


def test_contiene_secuencia_insegura_caracteres_control_y_nulo():
    assert contiene_secuencia_insegura("/api/test\x00malicioso")[0] is True
    assert contiene_secuencia_insegura("/api/test", raw_path=b"/api/test\x00")[0] is True
    assert contiene_secuencia_insegura("/api/test\r\neval")[0] is True


def test_middleware_rechaza_path_traversal_con_400():
    app = FastAPI()
    app.add_middleware(RechazoPathInseguroMiddleware)
    app.add_middleware(RequestIdMiddleware)

    @app.get("/{resto:path}")
    def catch_all(resto: str):
        return {"ok": True}

    client = TestClient(app, client=("203.0.113.5", 50000))
    with capture_logs() as logs:
        resp = client.get("/api/..;/.env")

    assert resp.status_code == 400
    assert resp.json() == {"detail": "Bad Request"}
    assert "X-Request-ID" in resp.headers

    rechazos = [ev for ev in logs if ev.get("event") == "rechazo_path_inseguro"]
    assert rechazos, "Se debió emitir el evento rechazo_path_inseguro"
    assert rechazos[0]["ip"] == "203.0.113.5"
    assert "traversal" in rechazos[0]["motivo"]


def test_middleware_permite_rutas_legitimas():
    app = FastAPI()
    app.add_middleware(RechazoPathInseguroMiddleware)
    app.add_middleware(RequestIdMiddleware)

    @app.get("/api/v1/ping")
    def ping():
        return {"pong": True}

    client = TestClient(app)
    resp = client.get("/api/v1/ping")
    assert resp.status_code == 200
    assert resp.json() == {"pong": True}


def test_rate_limit_404_bloquea_tras_superar_umbral():
    settings = Settings(
        RATE_LIMIT_404_MAX_INTENTOS=3,
        RATE_LIMIT_404_VENTANA_SEGUNDOS=60,
    )
    app = FastAPI()
    app.add_middleware(RateLimit404Middleware, settings=settings)

    @app.get("/ok")
    def ok():
        return PlainTextResponse("ok", status_code=200)

    @app.get("/no-existe")
    def no_existe():
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

    client = TestClient(app)
    ip_maliciosa = "198.51.100.10"
    client = TestClient(app, client=(ip_maliciosa, 50000))

    # Primeras 3 peticiones 404 son permitidas y registradas
    for _ in range(3):
        r = client.get("/no-existe")
        assert r.status_code == 404

    # La 4ta petición de la misma IP debe ser bloqueada inmediatamente con 429
    with capture_logs() as logs:
        r_bloqueada = client.get("/no-existe")

    assert r_bloqueada.status_code == 429
    assert r_bloqueada.json() == {"detail": "Demasiadas solicitudes no encontradas"}
    assert "Retry-After" in r_bloqueada.headers
    assert int(r_bloqueada.headers["Retry-After"]) > 0

    bloqueos = [ev for ev in logs if ev.get("event") == "rate_limit_404_bloqueado"]
    assert bloqueos, "Se debió emitir el log rate_limit_404_bloqueado"
    assert bloqueos[0]["ip"] == ip_maliciosa

    # Intentar falsear X-Forwarded-For no evade el rate limit porque el backend usa la IP real
    r_spoofed = client.get("/no-existe", headers={"X-Forwarded-For": "198.51.100.99"})
    assert r_spoofed.status_code == 429

    # Otra IP real diferente no está bloqueada
    client_otra_ip = TestClient(app, client=("198.51.100.99", 50000))
    r_otra_ip = client_otra_ip.get("/no-existe")
    assert r_otra_ip.status_code == 404


def test_rate_limit_404_resetea_con_peticion_exitosa():
    settings = Settings(
        RATE_LIMIT_404_MAX_INTENTOS=3,
        RATE_LIMIT_404_VENTANA_SEGUNDOS=60,
    )
    app = FastAPI()
    app.add_middleware(RateLimit404Middleware, settings=settings)

    @app.get("/ok")
    def ok():
        return PlainTextResponse("ok", status_code=200)

    @app.get("/no-existe")
    def no_existe():
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

    ip = "198.51.100.20"
    client = TestClient(app, client=(ip, 50000))

    # 2 peticiones 404
    client.get("/no-existe")
    client.get("/no-existe")

    # 1 petición 200 exitosa -> resetea contador
    r_ok = client.get("/ok")
    assert r_ok.status_code == 200

    # Puede hacer 2 peticiones 404 más sin ser bloqueado
    r1 = client.get("/no-existe")
    assert r1.status_code == 404
    r2 = client.get("/no-existe")
    assert r2.status_code == 404


def test_rate_limit_404_ignora_peticiones_autenticadas():
    settings = Settings(
        RATE_LIMIT_404_MAX_INTENTOS=2,
        RATE_LIMIT_404_VENTANA_SEGUNDOS=60,
    )
    app = FastAPI()
    app.add_middleware(RateLimit404Middleware, settings=settings)

    @app.get("/no-existe")
    def no_existe():
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

    client = TestClient(app, client=("198.51.100.30", 50000))
    headers_auth = {
        "Authorization": "Bearer token_valido",
    }

    # Varias peticiones 404 con header Authorization nunca bloquean al usuario
    for _ in range(5):
        r = client.get("/no-existe", headers=headers_auth)
        assert r.status_code == 404


def test_create_app_integracion_seguridad_rutas():
    settings = Settings(
        APP_ENV="test",
        DB_NAME="test_db",
        AUTH_REQUIRED=False,
    )
    app = create_app(settings)
    client = TestClient(app, raise_server_exceptions=False)

    # 1. Path traversal es rechazado tempranamente con 400
    r_traversal = client.get("/api/..;/.env")
    assert r_traversal.status_code == 400
    assert r_traversal.json() == {"detail": "Bad Request"}
    assert "X-Request-ID" in r_traversal.headers

    # 2. Ruta legítima responde 200 (liveness sin requerir BD)
    r_health = client.get("/health/live")
    assert r_health.status_code == 200

    # 3. Sonda sospechosa responde 404 y se loguea como sonda_sospechosa
    with capture_logs() as logs:
        r_sonda = client.get("/api/v1/.env")
    assert r_sonda.status_code == 404
    sondas = [ev for ev in logs if ev.get("event") == "sonda_sospechosa"]
    assert sondas, "Se esperaba evento sonda_sospechosa en create_app"
