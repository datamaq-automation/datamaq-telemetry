"""tests/unit/test_cargas_filtro_organizacion.py — Las cargas se filtran por la organización del token (#41).

Dos organizaciones (A y B), cada una con un medidor y una carga. Un usuario de A no ve las cargas ni las
lecturas de B; el superadmin ve las dos. El dispositivo se resuelve contra la misma regla que el resto de
los endpoints (device_ownership), con el YAML de plantas simulado.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.application.dtos.carga_dto import CargaResponseDTO
from src.application.use_cases.gestionar_acceso_plantas import GestionarAccesoPlantasUseCase
from src.domain.cargas.entities import NaturalezaElectrica, PatronOperacion
from src.domain.cargas.value_objects import CategoriaCarga
from src.domain.telemetria.entities import Planta
from src.infrastructure.fastapi import device_ownership
from src.infrastructure.fastapi.auth_dependencies import get_acceso_plantas_use_case
from src.infrastructure.fastapi.dependencies import get_cargas_use_case, get_usuario_actual
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.sqlalchemy.database import get_db_session

AHORA = datetime(2026, 10, 15, tzinfo=timezone.utc)


def _carga(carga_id: str, dispositivo_id: str) -> CargaResponseDTO:
    return CargaResponseDTO(
        id=carga_id,
        nombre=f"carga {carga_id}",
        dispositivo_id=dispositivo_id,
        categoria=CategoriaCarga.OTROS,
        naturaleza_electrica=NaturalezaElectrica.MIXTA,
        patron_operacion=PatronOperacion.INDETERMINADO,
        esta_caracterizada=False,
        activa=True,
        creado_en=AHORA,
        actualizado_en=AHORA,
    )


class _UseCaseFalso:
    def __init__(self, cargas: list[CargaResponseDTO]):
        self._cargas = cargas

    def listar_cargas(self, dispositivo_id=None, solo_activas=False):
        return list(self._cargas)

    def obtener_carga(self, carga_id):
        return next(c for c in self._cargas if c.id == carga_id)


@pytest.fixture
def dos_organizaciones(monkeypatch):
    dispositivos = {
        "dispositivo-a": SimpleNamespace(planta_id="planta-a"),
        "dispositivo-b": SimpleNamespace(planta_id="planta-b"),
    }
    plantas = {"planta-a": "org-a", "planta-b": "org-b"}

    class _RepoFalso:
        def obtener_por_id(self, id_):
            return dispositivos.get(id_)

        def obtener_por_uid(self, _uid):
            return None

    monkeypatch.setattr(device_ownership, "repo_dispositivos_resuelto", lambda db: _RepoFalso())
    monkeypatch.setattr(device_ownership, "_resolver_organizacion_planta", lambda planta_id: plantas.get(planta_id))
    return _UseCaseFalso([_carga("carga-a", "dispositivo-a"), _carga("carga-b", "dispositivo-b")])


def _acceso_sin_asignaciones() -> GestionarAccesoPlantasUseCase:
    """Sin filas en user_facility_access el usuario ve todas las plantas de su organización (#110)."""
    repo_accesos = MagicMock()
    repo_accesos.listar_por_usuario.return_value = []
    repo_org = MagicMock()
    repo_org.listar_plantas.return_value = [
        Planta(id="planta-a", organizacion_id="org-a", nombre="Planta A"),
        Planta(id="planta-b", organizacion_id="org-b", nombre="Planta B"),
    ]
    return GestionarAccesoPlantasUseCase(repo_accesos, repo_org)


def _cliente(rol: str, org: str | None, use_case: _UseCaseFalso) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "u-1", "rol": rol, "org": org}
    app.dependency_overrides[get_cargas_use_case] = lambda: use_case
    app.dependency_overrides[get_acceso_plantas_use_case] = _acceso_sin_asignaciones
    app.dependency_overrides[get_db_session] = lambda: None
    return TestClient(app)


def test_usuario_de_la_organizacion_a_solo_lista_sus_cargas(dos_organizaciones):
    client = _cliente("operador", "org-a", dos_organizaciones)

    resp = client.get("/api/v1/cargas")

    assert resp.status_code == 200
    assert [c["id"] for c in resp.json()] == ["carga-a"]


def test_superadmin_lista_las_cargas_de_todas_las_organizaciones(dos_organizaciones):
    client = _cliente("superadmin", "org-a", dos_organizaciones)

    resp = client.get("/api/v1/cargas")

    assert sorted(c["id"] for c in resp.json()) == ["carga-a", "carga-b"]


def test_usuario_de_a_no_lee_una_carga_de_b_por_id(dos_organizaciones):
    client = _cliente("operador", "org-a", dos_organizaciones)

    assert client.get("/api/v1/cargas/carga-a").status_code == 200
    assert client.get("/api/v1/cargas/carga-b").status_code == 404


def test_usuario_de_a_no_lee_el_perfil_ni_el_export_de_un_medidor_de_b(dos_organizaciones):
    client = _cliente("operador", "org-a", dos_organizaciones)

    assert client.get("/api/v1/cargas/intervalos?device_id=dispositivo-b").status_code == 404
    assert client.get("/api/v1/cargas/exportar/csv?dispositivo_id=dispositivo-b").status_code == 404


def test_superadmin_lee_la_carga_de_b_por_id(dos_organizaciones):
    client = _cliente("superadmin", "org-a", dos_organizaciones)

    assert client.get("/api/v1/cargas/carga-b").status_code == 200
