"""Fase G3 — Exception handler global devuelve 500 genérico sin exponer stack."""

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.infrastructure.fastapi.server import manejar_excepcion_no_mapeada


def _app_con_handler() -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(Exception, manejar_excepcion_no_mapeada)

    @app.get("/boom")
    def boom():
        raise Exception("secreto-del-stack")

    @app.get("/no-encontrado")
    def no_encontrado():
        raise HTTPException(status_code=404, detail="no_encontrado")

    return app


def test_excepcion_no_mapeada_devuelve_500_sin_detalles():
    client = TestClient(_app_con_handler(), raise_server_exceptions=False)
    respuesta = client.get("/boom")

    assert respuesta.status_code == 500
    assert respuesta.json() == {"detail": "error_interno"}
    assert "secreto-del-stack" not in respuesta.text


def test_http_exception_mapeada_no_se_convierte_en_500():
    client = TestClient(_app_con_handler(), raise_server_exceptions=False)
    respuesta = client.get("/no-encontrado")

    assert respuesta.status_code == 404
    assert respuesta.json() == {"detail": "no_encontrado"}


def test_excepcion_no_mapeada_db_loguea_estructurado_sin_fuga():
    from structlog.testing import capture_logs

    class DBErrorFake(Exception):
        orig = "1054: Unknown column"
        statement = "SELECT foo FROM bar"

    app = FastAPI()
    app.add_exception_handler(Exception, manejar_excepcion_no_mapeada)

    @app.get("/db-boom")
    def db_boom():
        raise DBErrorFake("fail")

    client = TestClient(app, raise_server_exceptions=False)
    with capture_logs() as logs:
        respuesta = client.get("/db-boom")

    assert respuesta.status_code == 500
    assert respuesta.json() == {"detail": "error_interno"}
    assert "Unknown column" not in respuesta.text
    errores = [ev for ev in logs if ev.get("event") == "excepcion_no_mapeada"]
    assert errores
    assert "Unknown column" in errores[0].get("db_error", "")
    assert "SELECT foo FROM bar" in errores[0].get("db_statement", "")
