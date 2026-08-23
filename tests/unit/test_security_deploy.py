"""Fase G6 — Despliegue seguro (TLS Mosquitto + documentación de WebSocket global)."""

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def test_mosquitto_allow_anonymous_false():
    contenido = (RAIZ / "deploy/mosquitto/mosquitto.conf").read_text(encoding="utf-8")
    assert "allow_anonymous false" in contenido


def test_mosquitto_tls_8883_activo():
    contenido = (RAIZ / "deploy/mosquitto/mosquitto.conf").read_text(encoding="utf-8")
    lineas = contenido.splitlines()
    lineas_8883 = [
        linea.strip()
        for linea in lineas
        if linea.strip().startswith("listener 8883") and not linea.lstrip().startswith("#")
    ]
    assert lineas_8883, "No hay un listener 8883 activo (sin comentar)"
    assert any("cafile" in linea for linea in lineas)
    assert any("certfile" in linea for linea in lineas)
    assert any("keyfile" in linea for linea in lineas)


def test_contrato_documenta_ws_global():
    contenido = (RAIZ / "docs/frontend-integration-guide.md").read_text(encoding="utf-8")
    assert "global" in contenido
    assert "WebSocket" in contenido
