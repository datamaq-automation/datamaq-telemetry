"""tests/integration/test_security_api.py — Auth obligatoria en routers y rol admin en purge."""

from src.infrastructure.fastapi.dependencies import (
    get_usuario_actual,
    requiere_rol_admin,
    requiere_rol_superadmin,
)
from src.infrastructure.fastapi.server import create_app


def _callables(dep) -> set:
    resultado = set()
    if getattr(dep, "call", None) is not None:
        resultado.add(dep.call)
    for sub in getattr(dep, "dependencies", None) or []:
        resultado |= _callables(sub)
    return resultado


def _aplanar(rutas) -> list:
    resultado = []
    for r in rutas:
        if hasattr(r, "original_router"):
            resultado.extend(_aplanar(r.original_router.routes))
        else:
            resultado.append(r)
    return resultado


def _rutas_api(app):
    return [
        r for r in _aplanar(app.routes) if hasattr(r, "path") and hasattr(r, "methods") and r.path.startswith("/api")
    ]


def test_create_app_requiere_auth_en_telemetria():
    app = create_app()
    rutas = [r for r in _rutas_api(app) if r.path.startswith("/api/v1/telemetria")]
    assert len(rutas) > 0
    for ruta in rutas:
        assert get_usuario_actual in _callables(ruta.dependant)


def test_purge_requiere_superadmin():
    # datamaq#119: la purga borra datos de todas las organizaciones; solo superadmin.
    app = create_app()
    purge = [r for r in _rutas_api(app) if r.path == "/api/v1/system/purge"]
    assert len(purge) == 1
    assert requiere_rol_superadmin in _callables(purge[0].dependant)
    assert requiere_rol_admin not in _callables(purge[0].dependant)


def test_login_y_health_son_publicos():
    app = create_app()
    publicos = ["/api/v1/auth/login", "/health"]
    for ruta in _rutas_api(app):
        if ruta.path in publicos:
            assert get_usuario_actual not in _callables(ruta.dependant)
