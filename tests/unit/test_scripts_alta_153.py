"""tests/unit/test_scripts_alta_153.py — issue #153: scripts de alta y vinculación de usuarios.

- seed_cliente.py: la fila espejo de organizations no lleva `name` (no es columna) y sí `es_cooperativa`.
- seed_cliente.py: --rol con roles válidos (superadmin y solo_lectura quedan fuera).
- gestionar_usuario_organizacion.py: aplicar_vinculacion usa dataclasses.replace (UsuarioAuth no tiene copy_with).
"""

import pytest

from scripts import gestionar_usuario_organizacion as gestion
from scripts import seed_cliente
from src.domain.auth.entities import UsuarioAuth
from src.infrastructure.sqlalchemy.models import OrganizationModel


def test_organizations_no_tiene_columna_name():
    # Documenta el fallo original: pasar name= al modelo lanza TypeError.
    with pytest.raises(TypeError):
        OrganizationModel(id="org-1", name="Cooperativa")


def test_fila_espejo_organizacion_lleva_es_cooperativa_sin_name():
    fila = seed_cliente.construir_fila_espejo_organizacion("org-1", True)
    assert isinstance(fila, OrganizationModel)
    assert fila.id == "org-1"
    assert fila.es_cooperativa is True


def test_fila_espejo_organizacion_default_no_cooperativa():
    fila = seed_cliente.construir_fila_espejo_organizacion("org-2", False)
    assert fila.es_cooperativa is False


def test_roles_de_alta_son_validos_y_excluyen_superadmin_y_solo_lectura():
    assert "operador" in seed_cliente.ROLES_ALTA
    assert "superadmin" not in seed_cliente.ROLES_ALTA
    assert "solo_lectura" not in seed_cliente.ROLES_ALTA
    assert set(seed_cliente.ROLES_ALTA) == {"operador", "admin", "mantenimiento", "ingeniero", "auditor"}


def test_usuario_auth_no_tiene_metodo_copy_with():
    # Documenta el fallo original en gestionar_usuario_organizacion:
    # UsuarioAuth es un dataclass estándar y carece del método copy_with.
    usr = UsuarioAuth(id="u1", usuario="ana@example.com", hash_contrasena="h", organizacion_id="org-1", rol="operador")
    assert not hasattr(usr, "copy_with")


def test_aplicar_vinculacion_devuelve_usuario_nuevo_sin_mutar_el_original():
    usr = UsuarioAuth(id="u1", usuario="ana@example.com", hash_contrasena="h", organizacion_id="org-1", rol="operador")

    nuevo = gestion.aplicar_vinculacion(usr, "org-2", "admin")

    assert nuevo.organizacion_id == "org-2"
    assert nuevo.rol == "admin"
    assert nuevo.id == "u1"
    assert usr.organizacion_id == "org-1"
    assert usr.rol == "operador"


@pytest.mark.parametrize("rol", seed_cliente.ROLES_ALTA)
def test_seed_cliente_parser_acepta_roles_permitidos(rol: str):
    parser = seed_cliente.construir_parser()
    args = parser.parse_args(["--org-nombre", "Org", "--planta-nombre", "P1", "--rol", rol])
    assert args.rol == rol


@pytest.mark.parametrize("rol_invalido", ["superadmin", "solo_lectura", "invalido", "root"])
def test_seed_cliente_parser_rechaza_roles_excluidos(rol_invalido: str):
    parser = seed_cliente.construir_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--org-nombre", "Org", "--planta-nombre", "P1", "--rol", rol_invalido])


def test_seed_cliente_parser_default_rol_es_operador():
    parser = seed_cliente.construir_parser()
    args = parser.parse_args(["--org-nombre", "Org", "--planta-nombre", "P1"])
    assert args.rol == "operador"
