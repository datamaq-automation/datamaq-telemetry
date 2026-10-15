"""tests/unit/test_matriz_roles.py — la matriz de roles generada desde las rutas está sincronizada con el código."""

import os
import subprocess
import sys

from scripts.generate_matriz_roles import ROLES_FUENTE, endpoints, guards_de_rol, leer_roles_validos

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
        "invitado",
        "invitado_global",
        "mantenimiento",
        "ingeniero",
        "auditor",
    }


def test_guards_dejan_pasar_exactamente_los_roles_que_su_codigo_dice():
    roles = leer_roles_validos()
    guards = guards_de_rol(roles)

    assert guards["requiere_rol_superadmin"] == {"superadmin"}
    assert guards["requiere_rol_admin"] == {"admin", "superadmin"}
    assert guards["requiere_rol_auditor_o_superadmin"] == {"auditor", "superadmin"}
    assert guards["requiere_rol_escritura"] == set(roles) - {"invitado", "invitado_global"}
    assert guards["no_permitido_para_invitados_2fa"] == set(roles) - {"invitado", "invitado_global"}


def test_cada_endpoint_tiene_su_guard_o_una_razon_para_no_tenerlo():
    eps = endpoints(leer_roles_validos())

    assert len(eps) > 100
    for ep in eps:
        assert ep.guards or ep.autenticacion, f"{ep.metodo} {ep.ruta} no declara auth ni guard"
