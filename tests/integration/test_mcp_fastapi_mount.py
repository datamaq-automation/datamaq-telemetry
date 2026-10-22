"""tests/integration/test_mcp_fastapi_mount.py — Test de integración para el montaje de FastMCP en FastAPI."""

from starlette.testclient import TestClient

from src.infrastructure.fastapi.server import create_app


def test_mcp_handshake_initialize() -> None:
    """Verifica que POST /mcp/ con handshake JSON-RPC initialize responde 200 text/event-stream."""
    app = create_app()

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "claude-client-test",
                "version": "1.0.0",
            },
        },
    }
    headers = {
        "Accept": "application/json, text/event-stream",
    }

    with TestClient(app) as client:
        response = client.post("/mcp/", json=payload, headers=headers)
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        assert "jsonrpc" in response.text
        assert "2.0" in response.text
        assert "protocolVersion" in response.text


def test_mcp_directo_sin_barra_final_ni_307() -> None:
    """Verifica que POST /mcp sin barra final responde directamente HTTP 200 text/event-stream sin 307."""
    app = create_app()

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "claude-client-test",
                "version": "1.0.0",
            },
        },
    }
    headers = {
        "Accept": "application/json, text/event-stream",
    }

    with TestClient(app) as client:
        response = client.post("/mcp", json=payload, headers=headers, follow_redirects=False)
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")


def test_mcp_listar_herramientas_via_http() -> None:
    """Verifica que tras initialize se pueden consultar las herramientas registradas en FastMCP vía HTTP."""
    app = create_app()

    init_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "claude-client-test",
                "version": "1.0.0",
            },
        },
    }
    headers = {
        "Accept": "application/json, text/event-stream",
    }

    with TestClient(app) as client:
        init_res = client.post("/mcp/", json=init_payload, headers=headers)
        assert init_res.status_code == 200
        session_id = init_res.headers.get("mcp-session-id")
        assert session_id is not None

        # Notificación de inicializado
        client.post(
            "/mcp/",
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers={"Accept": "application/json, text/event-stream", "mcp-session-id": session_id},
        )

        # tools/list
        tools_res = client.post(
            "/mcp/",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            headers={"Accept": "application/json, text/event-stream", "mcp-session-id": session_id},
        )
        assert tools_res.status_code == 200
        assert "datamaq_listar_plantas" in tools_res.text
        assert "datamaq_analizar_capacitores" in tools_res.text
        assert "datamaq_consultar_alertas" in tools_res.text
        assert "datamaq_consultar_penalizaciones" in tools_res.text
        assert "datamaq_consultar_potencia_reciente" in tools_res.text
