"""tests/unit/test_matriz_roles.py — la matriz de roles generada desde las rutas está sincronizada con el código."""

import os
import subprocess
import sys

from scripts.generate_matriz_roles import (
    ROLES_FUENTE,
    endpoints,
    generar,
    guards_de_rol,
    leer_roles_validos,
    main,
)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_matriz_roles_file_is_in_sync():
    cmd = [sys.executable, os.path.join(ROOT_DIR, "scripts", "generate_matriz_roles.py"), "--check"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"docs/matriz-roles-permisos.md está desactualizado:\n{result.stdout}"


def test_roles_validos_salen_de_la_fuente_de_autenticacion():
    roles = leer_roles_validos()

    assert ROLES_FUENTE.exists()
    assert set(roles) == {
        "superadmin",
        "admin",
        "operador",
        "mantenimiento",
        "ingeniero",
        "auditor",
        "solo_lectura",
    }


def test_guards_dejan_pasar_exactamente_los_roles_que_su_codigo_dice():
    roles = leer_roles_validos()
    guards = guards_de_rol(roles)

    assert guards["requiere_rol_superadmin"] == {"superadmin"}
    assert guards["requiere_rol_admin"] == {"admin", "superadmin"}
    assert guards["requiere_rol_auditor_o_superadmin"] == {"auditor", "superadmin"}
    # solo_lectura (decisión 2026-10-29) es el rol de la réplica: no pasa ningún guard de escritura.
    assert guards["requiere_rol_escritura"] == set(roles) - {"solo_lectura"}


def test_cada_endpoint_tiene_su_guard_o_una_razon_para_no_tenerlo():
    eps = endpoints(leer_roles_validos())

    assert len(eps) > 100
    for ep in eps:
        assert ep.guards or ep.autenticacion, f"{ep.metodo} {ep.ruta} no declara auth ni guard"


def test_insertar_lineas_en_blanco_en_router_no_desincroniza_la_matriz(tmp_path, monkeypatch):
    roles = leer_roles_validos()
    archivo_router = tmp_path / "dummy_router.py"
    monkeypatch.setattr("scripts.generate_matriz_roles.RUTAS_DIR", tmp_path)

    codigo_base = (
        "from fastapi import APIRouter, Depends\n"
        "from src.infrastructure.fastapi.dependencies import get_usuario_actual\n\n"
        "router = APIRouter(prefix='/api/v1/dummy')\n\n"
        "@router.get('/saludo')\n"
        "def saludo(user=Depends(get_usuario_actual)):\n"
        "    return {'msg': 'hola'}\n"
    )
    codigo_con_lineas_en_blanco = (
        "\n\n\nfrom fastapi import APIRouter, Depends\n\n\n\n\n"
        "from src.infrastructure.fastapi.dependencies import get_usuario_actual\n\n\n\n"
        "router = APIRouter(prefix='/api/v1/dummy')\n\n\n\n\n\n"
        "@router.get('/saludo')\n\n\n\n"
        "def saludo(user=Depends(get_usuario_actual)):\n\n"
        "    return {'msg': 'hola'}\n\n\n"
    )

    archivo_router.write_text(codigo_base, encoding="utf-8")
    eps_base = endpoints(roles)
    salida_base = generar()

    archivo_router.write_text(codigo_con_lineas_en_blanco, encoding="utf-8")
    eps_con_blancos = endpoints(roles)
    salida_con_blancos = generar()

    assert eps_base == eps_con_blancos
    assert salida_base == salida_con_blancos
    assert "dummy_router.py:saludo" in salida_base

    salida_md = tmp_path / "matriz-roles-permisos.md"
    monkeypatch.setattr("scripts.generate_matriz_roles.SALIDA", salida_md)
    archivo_router.write_text(codigo_base, encoding="utf-8")
    assert main([]) == 0
    archivo_router.write_text(codigo_con_lineas_en_blanco, encoding="utf-8")
    assert main(["--check"]) == 0
