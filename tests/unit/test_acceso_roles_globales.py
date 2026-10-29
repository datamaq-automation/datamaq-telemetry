"""tests/unit/test_acceso_roles_globales.py — Visibilidad global configurable (decisión 2026-10-29, opción B).

Regresión: con ROLES_ACCESO_GLOBAL_EXTRA vacío, solo_lectura ve solo su organización. Con
`solo_lectura` en la variable, ve todas. superadmin ve todas en ambos casos.
"""

from unittest.mock import MagicMock

import pytest

from src.application.use_cases.gestionar_acceso_plantas import GestionarAccesoPlantasUseCase
from src.domain.auth.services import ROLES_ACCESO_GLOBAL, PoliticaAccesoPlantasService, roles_de_acceso_global
from src.domain.telemetria.entities import Planta
from src.infrastructure.settings.config import Settings

ORG_A = "org-a"
ORG_B = "org-b"
PLANTAS = [
    Planta(id="pa1", organizacion_id=ORG_A, nombre="Casa"),
    Planta(id="pb1", organizacion_id=ORG_B, nombre="Durax"),
    Planta(id="pb2", organizacion_id=ORG_B, nombre="UPP"),
]


def _ids(resultado):
    return {p.id for p, _ in resultado}


def test_roles_de_acceso_global_vacio_devuelve_solo_superadmin():
    assert roles_de_acceso_global("") == ROLES_ACCESO_GLOBAL == frozenset({"superadmin"})


def test_roles_de_acceso_global_agrega_solo_lectura_desde_config():
    assert roles_de_acceso_global("solo_lectura") == frozenset({"superadmin", "solo_lectura"})
    assert roles_de_acceso_global(" solo_lectura , ") == frozenset({"superadmin", "solo_lectura"})


def test_sin_extra_solo_lectura_ve_solo_su_organizacion():
    resultado = PoliticaAccesoPlantasService.resolver("solo_lectura", ORG_A, PLANTAS, [])
    assert _ids(resultado) == {"pa1"}


def test_con_extra_solo_lectura_ve_todas_las_organizaciones():
    roles = roles_de_acceso_global("solo_lectura")
    resultado = PoliticaAccesoPlantasService.resolver("solo_lectura", ORG_A, PLANTAS, [], roles_globales=roles)
    assert _ids(resultado) == {"pa1", "pb1", "pb2"}


@pytest.mark.parametrize("extra", ["", "solo_lectura"])
def test_superadmin_ve_todas_con_o_sin_extra(extra):
    roles = roles_de_acceso_global(extra)
    resultado = PoliticaAccesoPlantasService.resolver("superadmin", ORG_A, PLANTAS, [], roles_globales=roles)
    assert _ids(resultado) == {"pa1", "pb1", "pb2"}


def test_caso_de_uso_con_extra_resuelve_todas_y_sin_extra_solo_la_propia():
    repo_accesos = MagicMock()
    repo_accesos.listar_por_usuario.return_value = []
    repo_org = MagicMock()
    repo_org.listar_plantas.return_value = PLANTAS

    sin_extra = GestionarAccesoPlantasUseCase(repo_accesos, repo_org, None, roles_de_acceso_global(""))
    con_extra = GestionarAccesoPlantasUseCase(repo_accesos, repo_org, None, roles_de_acceso_global("solo_lectura"))

    assert {p.id for p in sin_extra.resolver("u1", "solo_lectura", ORG_A)} == {"pa1"}
    assert {p.id for p in con_extra.resolver("u1", "solo_lectura", ORG_A)} == {"pa1", "pb1", "pb2"}


def test_produccion_rechaza_el_extra(monkeypatch):
    # Settings exige secretos fuertes en producción; el error del extra tiene que aparecer igual en el mensaje.
    with pytest.raises(Exception, match="ROLES_ACCESO_GLOBAL_EXTRA"):
        Settings(APP_ENV="production", ROLES_ACCESO_GLOBAL_EXTRA="solo_lectura", DEBUG=False)
