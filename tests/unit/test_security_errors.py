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
