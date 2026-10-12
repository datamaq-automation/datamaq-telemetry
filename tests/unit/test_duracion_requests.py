"""tests/unit/test_duracion_requests.py — Una línea INFO por request con ruta plantilla, estado, duración y request_id (#14)."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException
from starlette.testclient import TestClient

from src.infrastructure.fastapi.duracion_requests import RUTA_SIN_PLANTILLA, DuracionRequestMiddleware
from src.infrastructure.fastapi.middleware import RequestIdMiddleware


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/plantas/{planta_id}/unifilar/nodos/{nodo_id}/resumen")
    def resumen(planta_id: str, nodo_id: str) -> dict:
        return {"ok": True}

    @app.get("/falla")
    def falla() -> dict:
        raise HTTPException(status_code=503, detail="no")

    @app.get("/revienta")
    def revienta() -> dict:
        raise RuntimeError("bug")

    app.add_middleware(DuracionRequestMiddleware)
    app.add_middleware(RequestIdMiddleware)
    return app


@pytest.fixture
def registros():
    with patch("src.infrastructure.fastapi.duracion_requests.logger") as logger:
        yield logger


def _campos(logger) -> dict:
    logger.info.assert_called_once()
    (evento,) = logger.info.call_args.args
    assert evento == "http_request_completado"
    return logger.info.call_args.kwargs


def test_loguea_la_ruta_como_plantilla_sin_ids(registros):
    respuesta = TestClient(_app()).get("/plantas/p-123/unifilar/nodos/n-9/resumen")
    campos = _campos(registros)
    assert campos["ruta"] == "/plantas/{planta_id}/unifilar/nodos/{nodo_id}/resumen"
    assert campos["metodo"] == "GET"
    assert campos["estado_http"] == 200
    assert campos["duracion_ms"] >= 0
    assert campos["request_id"] == respuesta.headers["X-Request-ID"]


def test_loguea_el_estado_de_error(registros):
    TestClient(_app()).get("/falla")
    assert _campos(registros)["estado_http"] == 503


def test_excepcion_no_manejada_se_loguea_como_500(registros):
    TestClient(_app(), raise_server_exceptions=False).get("/revienta")
    assert _campos(registros)["estado_http"] == 500


def test_ruta_inexistente_no_inventa_plantilla(registros):
    TestClient(_app()).get("/no/existe/123")
    campos = _campos(registros)
    assert campos["ruta"] == RUTA_SIN_PLANTILLA
    assert campos["estado_http"] == 404


def test_la_app_real_registra_el_middleware_dentro_de_request_id():
    from src.infrastructure.fastapi.server import create_app

    clases = [m.cls for m in create_app().user_middleware]
    # user_middleware va de afuera hacia adentro: RequestId tiene que envolver a Duracion.
    assert clases.index(RequestIdMiddleware) < clases.index(DuracionRequestMiddleware)
