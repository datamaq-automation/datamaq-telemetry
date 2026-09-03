"""Verifica que create_app() registra el router de autenticación sin conexión a DB."""

from src.infrastructure.fastapi.dependencies import get_usuario_actual
from src.infrastructure.fastapi.server import create_app


def _rutas(app) -> list:
    resultado = []
    for ruta in app.routes:
        if hasattr(ruta, "original_router"):
            resultado.extend(ruta.original_router.routes)
        else:
            resultado.append(ruta)
    return resultado


def _callables(dep) -> set:
    resultado = set()
    if getattr(dep, "call", None) is not None:
        resultado.add(dep.call)
    for sub in getattr(dep, "dependencies", None) or []:
        resultado |= _callables(sub)
    return resultado


def test_create_app_registra_router_auth():
    app = create_app()
    rutas: dict[str, set[str]] = {}
    for ruta in app.routes:
        if hasattr(ruta, "methods") and hasattr(ruta, "path"):
            rutas.setdefault(ruta.path, set()).update(ruta.methods or set())
        elif hasattr(ruta, "original_router"):
            for subruta in ruta.original_router.routes:
                if hasattr(subruta, "methods") and hasattr(subruta, "path"):
                    rutas.setdefault(subruta.path, set()).update(subruta.methods or set())

    assert "/api/v1/auth/login" in rutas
    assert "POST" in rutas["/api/v1/auth/login"]


def test_create_app_registra_ruta_me():
    app = create_app()
    ruta_me = [r for r in _rutas(app) if r.path == "/api/v1/auth/me" and "GET" in (r.methods or set())]
    assert len(ruta_me) == 1


def test_me_protegido_por_get_usuario_actual():
    app = create_app()
    ruta_me = [r for r in _rutas(app) if r.path == "/api/v1/auth/me"]
    assert len(ruta_me) == 1
    assert get_usuario_actual in _callables(ruta_me[0].dependant)
