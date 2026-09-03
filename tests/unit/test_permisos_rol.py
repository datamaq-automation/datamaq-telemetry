"""Permisos por rol (D-04b): invitado de solo lectura en routers protegidos."""

import pytest
from fastapi import HTTPException

from src.infrastructure.fastapi import dependencies as deps
from src.infrastructure.fastapi.routes import (
    alertas_router,
    dispositivos_router,
    organizaciones_router,
    planes_router,
)


def _ruta(router, metodo: str, path: str):
    for ruta in router.routes:
        if metodo in ruta.methods and ruta.path == path:
            return ruta
    raise AssertionError(f"No existe {metodo} {path}")


def _dependencias(ruta) -> set:
    return {d.dependency for d in getattr(ruta, "dependencies", [])}


# P1 — requiere_rol_escritura rechaza invitado
def test_requiere_rol_escritura_rechaza_invitado():
    with pytest.raises(HTTPException) as e:
        deps.requiere_rol_escritura({"rol": "invitado"})

    assert e.value.status_code == 403
    assert e.value.detail == "forbidden"


# P2 — requiere_rol_escritura acepta admin y operador
def test_requiere_rol_escritura_acepta_admin_y_operador():
    assert deps.requiere_rol_escritura({"rol": "admin"}) == {"rol": "admin"}
    assert deps.requiere_rol_escritura({"rol": "operador"}) == {"rol": "operador"}


# P3 — endpoints de escritura exigen requiere_rol_escritura
def test_endpoints_escritura_exigen_rol_escritura():
    escrituras = [
        (dispositivos_router.router, "POST", "/api/v1/dispositivos"),
        (dispositivos_router.router, "PUT", "/api/v1/dispositivos/{device_id}"),
        (dispositivos_router.router, "PATCH", "/api/v1/dispositivos/{device_id}"),
        (organizaciones_router.router, "POST", "/api/v1/organizaciones"),
        (organizaciones_router.router, "POST", "/api/v1/plantas"),
        (planes_router.router, "POST", "/api/v1/planes"),
        (alertas_router.router, "POST", "/api/v1/alertas/{alerta_id}/resolver"),
    ]
    for router, metodo, path in escrituras:
        ruta = _ruta(router, metodo, path)
        assert deps.requiere_rol_escritura in _dependencias(ruta), f"{metodo} {path} sin requiere_rol_escritura"


# P4 — endpoints de lectura no exigen requiere_rol_escritura
def test_endpoints_lectura_no_exigen_rol_escritura():
    lecturas = [
        (dispositivos_router.router, "GET", "/api/v1/dispositivos"),
        (dispositivos_router.router, "GET", "/api/v1/dispositivos/{device_id}"),
        (organizaciones_router.router, "GET", "/api/v1/organizaciones"),
        (organizaciones_router.router, "GET", "/api/v1/plantas"),
        (planes_router.router, "GET", "/api/v1/planes"),
        (alertas_router.router, "GET", "/api/v1/alertas"),
    ]
    for router, metodo, path in lecturas:
        ruta = _ruta(router, metodo, path)
        assert deps.requiere_rol_escritura not in _dependencias(ruta), f"{metodo} {path} con requiere_rol_escritura"


# P5 — purge rechaza invitado vía requiere_rol_admin
def test_requiere_rol_admin_rechaza_invitado():
    with pytest.raises(HTTPException) as e:
        deps.requiere_rol_admin({"rol": "invitado"})

    assert e.value.status_code == 403
    assert e.value.detail == "forbidden"
