"""tests/unit/test_manejador_unifilar_invalido.py — Issue datamaq#148: manejador HTTP para EstructuraUnifilarInvalidaError.

Una consulta de unifilar sobre una planta con estructura inválida responde HTTP 500 con código semántico estable
y sin exponer detalles internos (ni nombres de nodos ni trazas crudas). El motivo y el id de la planta se registran
en los logs estructurados con X-Request-ID. Las demás excepciones no mapeadas siguen con el 500 genérico.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from src.domain.telemetria.exceptions import EstructuraUnifilarInvalidaError, NodoUnifilarNoEncontradoError
from src.infrastructure.fastapi.dependencies import (
    get_consultar_nodo_unifilar_use_case,
    get_planta_estructura_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.planta_ownership import resolver_planta_permitida
from src.infrastructure.fastapi.server import create_app

RUTA_RESUMEN = "/api/v1/plantas/planta-x/unifilar/nodos/n1/resumen?granularity=day&dias=7"
MOTIVO_INTERNO = "El nodo 'secreto-nodo-interno' referencia un padre inexistente 'fantasma-invalido'."


def _app_con_caso_de_uso(caso_de_uso: MagicMock):
    app = create_app()
    app.dependency_overrides[get_planta_estructura_use_case] = lambda: caso_de_uso
    app.dependency_overrides[get_consultar_nodo_unifilar_use_case] = lambda: caso_de_uso
    app.dependency_overrides[resolver_planta_permitida] = lambda planta_id=None: planta_id
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "u1", "rol": "superadmin", "org": "org-1"}
    return app


@pytest.fixture()
def caso_de_uso() -> MagicMock:
    mock = MagicMock()
    mock.potencia_referencia.return_value = None
    return mock


def test_planta_invalida_responde_500_con_codigo_y_mensaje_estable(caso_de_uso):
    caso_de_uso.resumen.side_effect = EstructuraUnifilarInvalidaError(MOTIVO_INTERNO, planta_id="planta-x")
    client = TestClient(_app_con_caso_de_uso(caso_de_uso))

    response = client.get(RUTA_RESUMEN)

    assert response.status_code == 500
    cuerpo = response.json()
    assert cuerpo == {
        "codigo": "unifilar_invalido",
        "mensaje": "La estructura del unifilar de la planta no es válida.",
    }
    assert response.headers.get("X-Request-ID") is not None
    assert len(response.headers["X-Request-ID"]) == 32
    assert "secreto-nodo-interno" not in response.text
    assert "fantasma-invalido" not in response.text
    assert "Traceback" not in response.text


def test_planta_invalida_registra_error_estructurado_con_contexto(caso_de_uso):
    caso_de_uso.resumen.side_effect = EstructuraUnifilarInvalidaError(MOTIVO_INTERNO, planta_id="planta-x")
    client = TestClient(_app_con_caso_de_uso(caso_de_uso))

    with capture_logs() as logs:
        response = client.get(RUTA_RESUMEN)

    registros = [r for r in logs if r.get("event") == "estructura_unifilar_invalida"]
    assert len(registros) == 1
    reg = registros[0]
    assert reg["log_level"] == "error"
    assert reg["planta_id"] == "planta-x"
    assert reg["motivo"] == MOTIVO_INTERNO
    assert reg["ruta"] == "/api/v1/plantas/planta-x/unifilar/nodos/n1/resumen"
    assert reg["metodo"] == "GET"
    assert reg["request_id"] == response.headers["X-Request-ID"]


def test_planta_invalida_extrae_planta_id_de_path_params_si_no_esta_en_excepcion(caso_de_uso):
    caso_de_uso.resumen.side_effect = EstructuraUnifilarInvalidaError(MOTIVO_INTERNO)
    client = TestClient(_app_con_caso_de_uso(caso_de_uso))

    with capture_logs() as logs:
        response = client.get(RUTA_RESUMEN)

    assert response.status_code == 500
    registros = [r for r in logs if r.get("event") == "estructura_unifilar_invalida"]
    assert len(registros) == 1
    assert registros[0]["planta_id"] == "planta-x"


def test_excepcion_no_mapeada_sigue_en_el_manejador_generico(caso_de_uso):
    caso_de_uso.resumen.side_effect = RuntimeError("fallo inesperado del sistema")
    client = TestClient(_app_con_caso_de_uso(caso_de_uso), raise_server_exceptions=False)

    response = client.get(RUTA_RESUMEN)

    assert response.status_code == 500
    assert response.json() == {"detail": "Ocurrió un error interno en el servidor"}
    assert "unifilar_invalido" not in response.text


def test_error_de_nodo_no_encontrado_mantiene_404(caso_de_uso):
    caso_de_uso.resumen.side_effect = NodoUnifilarNoEncontradoError(
        "El nodo 'n1' no existe en el unifilar de la planta."
    )
    client = TestClient(_app_con_caso_de_uso(caso_de_uso), raise_server_exceptions=False)

    response = client.get(RUTA_RESUMEN)

    assert response.status_code == 404
    assert response.json() == {"detail": "El nodo 'n1' no existe en el unifilar de la planta."}


def test_endpoint_unifilar_planta_responde_500_si_estructura_invalida(caso_de_uso):
    caso_de_uso.obtener_unifilar.side_effect = EstructuraUnifilarInvalidaError(
        "Ciclo detectado en topología", planta_id="planta-beta"
    )
    client = TestClient(_app_con_caso_de_uso(caso_de_uso))

    response = client.get("/api/v1/plantas/planta-beta/unifilar")

    assert response.status_code == 500
    assert response.json() == {
        "codigo": "unifilar_invalido",
        "mensaje": "La estructura del unifilar de la planta no es válida.",
    }


@pytest.mark.asyncio
async def test_manejador_re_lanza_si_no_es_estructura_unifilar_invalida():
    from unittest.mock import AsyncMock

    from src.infrastructure.fastapi.error_handler import manejar_estructura_unifilar_invalida

    req = AsyncMock()
    with pytest.raises(ValueError, match="otra_cosa"):
        await manejar_estructura_unifilar_invalida(req, ValueError("otra_cosa"))
