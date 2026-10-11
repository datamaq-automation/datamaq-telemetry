"""tools/mcp/test_server.py — Pruebas unitarias para el Servidor MCP DataMaq."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from mcp.server.fastmcp import Context

from tools.mcp.server import (
    datamaq_analizar_capacitores,
    datamaq_consultar_alertas,
    datamaq_consultar_penalizaciones,
    datamaq_consultar_potencia_reciente,
    datamaq_listar_plantas,
    mcp,
    set_client,
)


@pytest.fixture(autouse=True)
def limpiar_cliente():
    """Restaura el estado del cliente HTTP tras cada prueba."""
    yield
    set_client(None)


def test_herramientas_registradas():
    """Valida que las 5 herramientas de diagnóstico requeridas estén registradas."""
    tools = mcp._tool_manager.list_tools()
    nombres_herramientas = {t.name for t in tools}

    esperadas = {
        "datamaq_listar_plantas",
        "datamaq_consultar_alertas",
        "datamaq_analizar_capacitores",
        "datamaq_consultar_penalizaciones",
        "datamaq_consultar_potencia_reciente",
    }
    assert esperadas.issubset(nombres_herramientas), f"Faltan herramientas: {esperadas - nombres_herramientas}"


@pytest.mark.asyncio
async def test_datamaq_listar_plantas():
    """Prueba datamaq_listar_plantas con MockTransport y validación de token Bearer."""
    solicitudes_recibidas: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        solicitudes_recibidas.append(request)
        assert request.url.path == "/api/v1/plantas"
        assert request.headers.get("Authorization") == "Bearer token-secreto-123"
        return httpx.Response(
            200,
            json=[
                {"id": "planta-alpha", "nombre": "Planta Alpha", "organizacion_id": "org-1"},
                {"id": "planta-beta", "nombre": "Planta Beta", "organizacion_id": "org-1"},
            ],
        )

    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://datamaq.local",
        headers={"Authorization": "Bearer token-secreto-123"},
    )
    set_client(mock_client)

    plantas = await datamaq_listar_plantas()

    assert len(plantas) == 2
    assert plantas[0]["id"] == "planta-alpha"
    assert plantas[1]["nombre"] == "Planta Beta"
    assert len(solicitudes_recibidas) == 1


@pytest.mark.asyncio
async def test_datamaq_consultar_alertas():
    """Prueba datamaq_consultar_alertas con filtros de planta, enriquecimiento y salvaguarda."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/dispositivos":
            assert request.url.params.get("planta_id") == "planta-pacheco"
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "medidor-01",
                        "ubicacion_tag": "TGBT General",
                        "nombre": "Medidor Principal",
                        "planta_id": "planta-pacheco",
                    }
                ],
            )
        if request.url.path == "/api/v1/alertas":
            assert request.url.params.get("planta_id") == "planta-pacheco"
            assert request.url.params.get("solo_abiertas") == "true"
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 101,
                        "dispositivo_id": "medidor-01",
                        "tipo_alerta": "BAJO_FACTOR_POTENCIA",
                        "severidad": "WARNING",
                        "mensaje": "Factor de potencia por debajo de 0.85 sostenido",
                        "esta_resuelta": False,
                    },
                    {
                        "id": 999,
                        "dispositivo_id": "medidor-ajeno",
                        "tipo_alerta": "TENSION_ALTA",
                        "severidad": "CRITICAL",
                        "mensaje": "Alerta que no pertenece a planta-pacheco",
                        "esta_resuelta": False,
                    },
                ],
            )
        return httpx.Response(404, json={"detail": "Not found"})

    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://datamaq.local",
    )
    set_client(mock_client)

    alertas = await datamaq_consultar_alertas(planta_id="planta-pacheco", solo_abiertas=True)

    assert len(alertas) == 1
    assert alertas[0]["id"] == 101
    assert alertas[0]["tipo_alerta"] == "BAJO_FACTOR_POTENCIA"
    assert alertas[0]["planta_id"] == "planta-pacheco"
    assert alertas[0]["dispositivo_tag"] == "TGBT General"


@pytest.mark.asyncio
async def test_datamaq_analizar_capacitores():
    """Prueba datamaq_analizar_capacitores retornando cálculo SSOT de compensación."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/analitica/banco-capacitores/planta"
        assert request.url.params.get("planta_id") == "planta-pacheco"
        assert request.url.params.get("periodo_dias") == "30"
        return httpx.Response(
            200,
            json={
                "planta_id": "planta-pacheco",
                "periodo_dias": 30,
                "potencia_activa_promedio_kw": 125.4,
                "potencia_reactiva_promedio_kvar": 58.2,
                "potencia_reactiva_max_kvar": 85.0,
                "fp_promedio": 0.88,
                "fp_objetivo": 0.96,
                "qc_necesaria_kvar": 21.6,
                "banco_comercial_sugerido_kvar": 25.0,
                "escalones_sugeridos_kvar": [10.0, 15.0],
                "sobrecompensacion_sostenida": False,
                "razon_no_recomendacion": None,
                "fecha_calculo": "2026-10-10T12:00:00Z",
            },
        )

    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://datamaq.local",
    )
    set_client(mock_client)

    resultado = await datamaq_analizar_capacitores(planta_id="planta-pacheco", periodo_dias=30)

    assert resultado["planta_id"] == "planta-pacheco"
    assert resultado["banco_comercial_sugerido_kvar"] == 25.0
    assert resultado["escalones_sugeridos_kvar"] == [10.0, 15.0]
    assert resultado["fp_promedio"] == 0.88


@pytest.mark.asyncio
async def test_datamaq_consultar_penalizaciones():
    """Prueba datamaq_consultar_penalizaciones con recargos calculados."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/analitica/penalizaciones/planta"
        assert request.url.params.get("planta_id") == "planta-pacheco"
        assert request.url.params.get("periodo_dias") == "7"
        return httpx.Response(
            200,
            json={
                "planta_id": "planta-pacheco",
                "periodo_dias": 7,
                "intervalos_bajo_fp_count": 58,
                "horas_bajo_fp": 14.5,
                "penalizacion_estimada_ars": 45200.50,
                "moneda": "ARS",
                "timestamp_calculo": "2026-10-10T12:00:00Z",
            },
        )

    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://datamaq.local",
    )
    set_client(mock_client)

    penalizaciones = await datamaq_consultar_penalizaciones(planta_id="planta-pacheco", periodo_dias=7)

    assert penalizaciones["planta_id"] == "planta-pacheco"
    assert penalizaciones["penalizacion_estimada_ars"] == 45200.50
    assert penalizaciones["horas_bajo_fp"] == 14.5


def _handler_potencia(lecturas_por_id: dict[str, Any], errores: set[str] | None = None):
    """Mock de la API: lista de dispositivos de la planta y serie instantánea por dispositivo."""
    errores = errores or set()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/dispositivos":
            assert request.url.params.get("planta_id") == "planta-pacheco"
            return httpx.Response(200, json=[{"id": dev} for dev in lecturas_por_id])
        prefijo = "/api/v1/telemetria/instantaneous/"
        assert request.url.path.startswith(prefijo)
        dev = request.url.path[len(prefijo) :]
        assert request.url.params.get("granularity") == "5m"
        if dev in errores:
            return httpx.Response(404, json={"detail": "no existe"})
        return httpx.Response(200, json=lecturas_por_id[dev])

    return handler


def _lectura(registrado_en: str, p_w: float, q_var: float, fp: float) -> dict[str, Any]:
    return {
        "registrado_en": registrado_en,
        "potencia_activa_total_W": p_w,
        "potencia_reactiva_total_VAR": q_var,
        "factor_potencia_total": fp,
    }


@pytest.mark.asyncio
async def test_datamaq_consultar_potencia_reciente_suma_dispositivos_por_bucket():
    """La planta suma P y Q de sus dispositivos por bucket de 5 min, no promedia dispositivos sueltos."""
    lecturas = {
        "d1": [
            _lectura("2026-10-10T12:00:00Z", 100_000.0, 50_000.0, 0.89),
            _lectura("2026-10-10T12:05:00Z", 120_000.0, 60_000.0, 0.93),
        ],
        "d2": [_lectura("2026-10-10T12:00:30Z", 50_000.0, 30_000.0, 0.91)],
    }
    set_client(
        httpx.AsyncClient(transport=httpx.MockTransport(_handler_potencia(lecturas)), base_url="http://datamaq.local")
    )
    resumen = await datamaq_consultar_potencia_reciente(planta_id="planta-pacheco", horas=24)
    # Bucket 12:00 = 150 kW / 80 kvar (d1+d2); bucket 12:05 = 120 kW / 60 kvar (solo d1)
    assert resumen["dispositivos_consultados"] == 2
    assert resumen["dispositivos_con_error"] == []
    assert resumen["puntos_medicion_count"] == 2
    assert resumen["potencia_activa_promedio_kw"] == 135.0
    assert resumen["potencia_activa_max_kw"] == 150.0
    assert resumen["potencia_reactiva_promedio_kvar"] == 70.0
    assert resumen["potencia_reactiva_max_kvar"] == 80.0
    assert resumen["factor_potencia_promedio"] == pytest.approx(0.915, abs=1e-3)


@pytest.mark.asyncio
async def test_datamaq_consultar_potencia_reciente_dispositivo_con_error_no_corta():
    """Un dispositivo que responde 404 se reporta y no tumba la consulta de la planta."""
    lecturas = {"d1": [_lectura("2026-10-10T12:00:00Z", 80_000.0, 40_000.0, 0.9)], "d2": []}
    handler = _handler_potencia(lecturas, errores={"d2"})
    set_client(httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://datamaq.local"))
    resumen = await datamaq_consultar_potencia_reciente(planta_id="planta-pacheco", horas=24)
    assert resumen["dispositivos_con_error"] == ["d2"]
    assert resumen["potencia_activa_promedio_kw"] == 80.0


@pytest.mark.asyncio
async def test_datamaq_consultar_potencia_reciente_planta_sin_dispositivos():
    set_client(httpx.AsyncClient(transport=httpx.MockTransport(_handler_potencia({})), base_url="http://datamaq.local"))
    resumen = await datamaq_consultar_potencia_reciente(planta_id="planta-pacheco", horas=24)
    assert resumen["dispositivos_consultados"] == 0
    assert resumen["puntos_medicion_count"] == 0
    assert resumen["potencia_activa_promedio_kw"] is None


@pytest.mark.asyncio
async def test_manejo_errores_401_no_autorizado():
    """Verifica que un error 401 proporcione un mensaje claro sobre autenticación."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Token expirado o ausente"})

    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://datamaq.local",
    )
    set_client(mock_client)

    with pytest.raises(RuntimeError) as exc_info:
        await datamaq_listar_plantas()

    assert "401" in str(exc_info.value)
    assert "DATAMAQ_AUTH_TOKEN" in str(exc_info.value)


@pytest.mark.asyncio
async def test_manejo_errores_404_no_encontrado():
    """Verifica que un error 404 identifique claramente la ausencia del recurso."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Planta inexistente"})

    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://datamaq.local",
    )
    set_client(mock_client)

    with pytest.raises(RuntimeError) as exc_info:
        await datamaq_analizar_capacitores(planta_id="planta-fantasma")

    assert "404" in str(exc_info.value)
    assert "Planta inexistente" in str(exc_info.value)


@pytest.mark.asyncio
async def test_propagacion_token_desde_context_header():
    """Valida que el header Authorization recibido en FastMCP Context se propague como Bearer token."""
    header_recibido: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        header_recibido.append(request.headers.get("authorization"))
        return httpx.Response(200, json=[{"planta_id": "planta-test"}])

    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://datamaq.local",
    )
    set_client(mock_client)

    mock_ctx = MagicMock(spec=Context)
    mock_request = MagicMock()
    mock_request.headers = {"authorization": "Bearer oauth-dynamic-token-xyz"}
    mock_ctx.request_context.request = mock_request

    resultado = await datamaq_listar_plantas(ctx=mock_ctx)

    assert len(resultado) == 1
    assert header_recibido == ["Bearer oauth-dynamic-token-xyz"]


@pytest.mark.asyncio
async def test_propagacion_token_desde_variable_entorno(monkeypatch: pytest.MonkeyPatch):
    """Valida que si no hay Context, se use DATAMAQ_AUTH_TOKEN de entorno."""
    monkeypatch.setenv("DATAMAQ_AUTH_TOKEN", "token-desde-env-123")
    header_recibido: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        header_recibido.append(request.headers.get("authorization"))
        return httpx.Response(200, json=[{"planta_id": "planta-test"}])

    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://datamaq.local",
    )
    set_client(mock_client)

    resultado = await datamaq_listar_plantas(ctx=None)

    assert len(resultado) == 1
    assert header_recibido == ["Bearer token-desde-env-123"]


@pytest.mark.asyncio
async def test_prioridad_header_sobre_variable_entorno(monkeypatch: pytest.MonkeyPatch):
    """Valida que el header en Context tenga precedencia sobre DATAMAQ_AUTH_TOKEN."""
    monkeypatch.setenv("DATAMAQ_AUTH_TOKEN", "token-env-ignorado")
    header_recibido: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        header_recibido.append(request.headers.get("authorization"))
        return httpx.Response(200, json=[{"planta_id": "planta-test"}])

    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://datamaq.local",
    )
    set_client(mock_client)

    mock_ctx = MagicMock(spec=Context)
    mock_request = MagicMock()
    mock_request.headers = {"authorization": "Bearer token-header-prioritario"}
    mock_ctx.request_context.request = mock_request

    resultado = await datamaq_listar_plantas(ctx=mock_ctx)

    assert len(resultado) == 1
    assert header_recibido == ["Bearer token-header-prioritario"]


@pytest.mark.asyncio
async def test_error_sin_token_cuando_no_hay_cliente_mock(monkeypatch: pytest.MonkeyPatch):
    """Valida que se emita error 401 si no hay token (ni header ni env) y no hay cliente mock."""
    monkeypatch.delenv("DATAMAQ_AUTH_TOKEN", raising=False)
    set_client(None)

    with pytest.raises(RuntimeError) as exc_info:
        await datamaq_listar_plantas(ctx=None)

    assert "Error 401 (No autorizado)" in str(exc_info.value)
    assert "DATAMAQ_AUTH_TOKEN" in str(exc_info.value)


def test_archivo_claude_desktop_config_valido():
    """Valida la integridad del archivo de configuración claude_desktop_config.json."""
    config_path = Path(__file__).parent / "claude_desktop_config.json"
    assert config_path.exists(), "El archivo claude_desktop_config.json no existe"

    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    assert "mcpServers" in config
    assert "datamaq" in config["mcpServers"]
    datamaq_cfg = config["mcpServers"]["datamaq"]
    assert datamaq_cfg["command"] == "python"
    assert datamaq_cfg["args"] == ["-m", "tools.mcp.server"]
    assert "env" in datamaq_cfg
    assert "DATAMAQ_API_URL" in datamaq_cfg["env"]
    assert "DATAMAQ_AUTH_TOKEN" in datamaq_cfg["env"]


def test_servidor_arranque_stdio():
    """Verifica que el servidor arranque en modo stdio y responda a 'initialize' de MCP."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "tools.mcp.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "DATAMAQ_API_URL": "http://localhost:8000"},
    )

    peticion_init: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"},
        },
    }

    try:
        assert proc.stdin is not None
        proc.stdin.write(json.dumps(peticion_init) + "\n")
        proc.stdin.flush()

        assert proc.stdout is not None
        linea = proc.stdout.readline()
        assert linea, "El servidor no respondió por stdout"

        respuesta = json.loads(linea)
        assert respuesta.get("id") == 1
        assert "result" in respuesta
        assert respuesta["result"]["serverInfo"]["name"] == "datamaq-mcp"
        assert "tools" in respuesta["result"]["capabilities"]
    finally:
        proc.terminate()
        proc.wait(timeout=3)
