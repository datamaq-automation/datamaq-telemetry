"""Verifica que create_app() registra el router de disponibilidad de máquina sin conexión a DB."""

from src.infrastructure.fastapi.server import create_app


def test_create_app_registra_router_disponibilidad():
    app = create_app()
    rutas: dict[str, set[str]] = {}
    for ruta in app.routes:
        if hasattr(ruta, "methods") and hasattr(ruta, "path"):
            rutas.setdefault(ruta.path, set()).update(ruta.methods or set())
        elif hasattr(ruta, "original_router"):
            for subruta in ruta.original_router.routes:
                if hasattr(subruta, "methods") and hasattr(subruta, "path"):
                    rutas.setdefault(subruta.path, set()).update(subruta.methods or set())

    assert "/api/v1/disponibilidad/maquinas" in rutas
    assert "GET" in rutas["/api/v1/disponibilidad/maquinas"]
    assert "POST" in rutas["/api/v1/disponibilidad/maquinas"]
    assert "/api/v1/disponibilidad/maquinas/{maquina_id}/histograma" in rutas
    assert "/api/v1/disponibilidad/maquinas/{maquina_id}/eventos" in rutas
    assert "/api/v1/disponibilidad/eventos/{evento_id}/corregir" in rutas
    assert "POST" in rutas["/api/v1/disponibilidad/eventos/{evento_id}/corregir"]
    assert "/api/v1/disponibilidad/paradas-programadas" in rutas
