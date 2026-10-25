"""Compatibilidad temporal de los roles invitado e invitado_global (TODO #65).

Solo se acepta el rol en /me y en el check de 2FA. No dan escritura ni acceso global:
este test fija que la compatibilidad no se usa como permiso.
"""

import pytest
from fastapi import HTTPException

from src.domain.auth.services import ROLES_ACCESO_GLOBAL
from src.infrastructure.fastapi.dependencies import requiere_rol_escritura

ROLES_COMPAT = ("invitado", "invitado_global")


@pytest.mark.parametrize("rol", ROLES_COMPAT)
def test_rol_de_compatibilidad_no_escribe(rol):
    with pytest.raises(HTTPException) as exc:
        requiere_rol_escritura({"usuario": "u1", "rol": rol})
    assert exc.value.status_code == 403


@pytest.mark.parametrize("rol", ROLES_COMPAT)
def test_rol_de_compatibilidad_no_tiene_acceso_global(rol):
    assert rol not in ROLES_ACCESO_GLOBAL
