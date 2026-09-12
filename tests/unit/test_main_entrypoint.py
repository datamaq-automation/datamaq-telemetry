"""tests/unit/test_main_entrypoint.py — Pruebas del entrypoint ASGI (main.py)."""

import src.main


def test_main_crea_app():
    app = src.main.app

    assert app is not None
    assert app.title == "Datamaq Telemetry Platform API"
