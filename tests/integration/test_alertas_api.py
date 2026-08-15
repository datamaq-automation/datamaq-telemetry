"""Verifica que create_app() registra el router de alertas sin conexión a DB."""

from src.infrastructure.fastapi.server import create_app


def test_create_app_registra_router_alertas():
    app = create_app()
    rutas: dict[str, set[str]] = {}
    for ruta in app.routes:
        if hasattr(ruta, "methods") and hasattr(ruta, "path"):
            rutas.setdefault(ruta.path, set()).update(ruta.methods or set())
        elif hasattr(ruta, "original_router"):
            for subruta in ruta.original_router.routes:
                if hasattr(subruta, "methods") and hasattr(subruta, "path"):
                    rutas.setdefault(subruta.path, set()).update(subruta.methods or set())

    assert "/api/alertas" in rutas
    assert "GET" in rutas["/api/alertas"]
    assert "/api/alertas/{alerta_id}/resolver" in rutas
    assert "POST" in rutas["/api/alertas/{alerta_id}/resolver"]
