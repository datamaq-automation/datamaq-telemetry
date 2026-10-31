"""tests/unit/test_cargas_asignacion_parcial.py — sec(cargas), Issue datamaq#110.

Un usuario con asignación parcial de plantas (user_facility_access) no puede operar cargas, campañas ni
intervalos de una planta no asignada, aunque sea de su misma organización. El resto de los routers ya lo
aplica por el Depends de router; las verificaciones imperativas de cargas_router debían aplicarlo también.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.application.dtos.carga_dto import CampanaResponseDTO, CargaResponseDTO, IntervaloActividadResponseDTO
from src.application.use_cases.gestionar_acceso_plantas import GestionarAccesoPlantasUseCase
from src.domain.auth.entities import AccesoPlantaUsuario
from src.domain.auth.ports import RepositorioAccesosPlantaPort
from src.domain.cargas.value_objects import (
    CategoriaCarga,
    EstadoCampana,
    NaturalezaElectrica,
    PatronOperacion,
    TipoCampana,
)
from src.domain.telemetria.entities import Planta
from src.infrastructure.fastapi import device_ownership
from src.infrastructure.fastapi.auth_dependencies import get_acceso_plantas_use_case
from src.infrastructure.fastapi.dependencies import (
    get_atribucion_use_case,
    get_caracterizacion_use_case,
    get_cargas_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.sqlalchemy.database import get_db_session

AHORA = datetime(2026, 10, 15, tzinfo=timezone.utc)
USUARIO = {"sub": "u-1", "rol": "operador", "org": "org-a"}


class _RepoAccesosEnMemoria(RepositorioAccesosPlantaPort):
    def __init__(self, accesos: list[AccesoPlantaUsuario]) -> None:
        self.accesos = accesos

    def listar_por_usuario(self, usuario_id: str) -> list[AccesoPlantaUsuario]:
        return [a for a in self.accesos if a.usuario_id == usuario_id]

    def reemplazar(self, usuario_id: str, accesos: list[AccesoPlantaUsuario]) -> list[AccesoPlantaUsuario]:
        raise NotImplementedError


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


def _campana(campana_id: str, dispositivo_id: str) -> CampanaResponseDTO:
    return CampanaResponseDTO(
        id=campana_id,
        dispositivo_id=dispositivo_id,
        tipo=TipoCampana.ACTIVA,
        estado=EstadoCampana.EN_CURSO,
        inicio_at=AHORA,
        fin_planificado_at=AHORA,
        duracion_planificada_s=120.0,
    )


def _intervalo(intervalo_id: int, dispositivo_id: str) -> IntervaloActividadResponseDTO:
    return IntervaloActividadResponseDTO(
        id=intervalo_id,
        dispositivo_id=dispositivo_id,
        inicio_at=AHORA,
        fin_at=AHORA,
        duracion_segundos=60.0,
    )


@pytest.fixture
def org_con_asignacion_parcial(monkeypatch):
    """Org A con dos plantas. El usuario solo tiene asignada planta-a1; dispositivo-a2 es de planta-a2."""
    dispositivos = {
        "dispositivo-a1": SimpleNamespace(planta_id="planta-a1"),
        "dispositivo-a2": SimpleNamespace(planta_id="planta-a2"),
    }
    plantas_org = {"planta-a1": "org-a", "planta-a2": "org-a"}

    class _RepoDispositivosFalso:
        def obtener_por_id(self, id_):
            return dispositivos.get(id_)

        def obtener_por_uid(self, _uid):
            return None

    monkeypatch.setattr(device_ownership, "repo_dispositivos_resuelto", lambda db: _RepoDispositivosFalso())
    monkeypatch.setattr(device_ownership, "_resolver_organizacion_planta", lambda planta_id: plantas_org.get(planta_id))

    repo_org = MagicMock()
    repo_org.listar_plantas.return_value = [
        Planta(id="planta-a1", organizacion_id="org-a", nombre="Planta A1"),
        Planta(id="planta-a2", organizacion_id="org-a", nombre="Planta A2"),
    ]
    acceso = GestionarAccesoPlantasUseCase(
        _RepoAccesosEnMemoria([AccesoPlantaUsuario("u-1", "planta-a1", puede_cambiar=False)]),
        repo_org,
    )

    cargas = MagicMock()
    cargas.obtener_carga.side_effect = lambda carga_id: {
        "carga-a1": _carga("carga-a1", "dispositivo-a1"),
        "carga-a2": _carga("carga-a2", "dispositivo-a2"),
    }[carga_id]
    cargas.actualizar_carga.side_effect = lambda carga_id, _dto: _carga(carga_id, "dispositivo-a2")
    cargas.registrar_carga.side_effect = lambda dto: _carga("nueva", dto.dispositivo_id)
    cargas.listar_cargas.return_value = [_carga("carga-a1", "dispositivo-a1"), _carga("carga-a2", "dispositivo-a2")]

    caracterizacion = MagicMock()
    caracterizacion.obtener.side_effect = lambda campana_id: _campana(campana_id, "dispositivo-a2")
    caracterizacion.iniciar_activa.side_effect = lambda dto, usuario_id=None: _campana("nueva", dto.dispositivo_id)

    atribucion = MagicMock()
    atribucion.dispositivo_de_intervalo.side_effect = lambda intervalo_id: {1: "dispositivo-a1", 2: "dispositivo-a2"}[
        intervalo_id
    ]
    atribucion.corregir_intervalo.side_effect = lambda intervalo_id, _dto, usuario_id=None: _intervalo(
        intervalo_id, "dispositivo-a2"
    )

    return SimpleNamespace(
        acceso=acceso,
        cargas=cargas,
        caracterizacion=caracterizacion,
        atribucion=atribucion,
    )


def _cliente(mocks: SimpleNamespace) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_usuario_actual] = lambda: USUARIO
    app.dependency_overrides[get_acceso_plantas_use_case] = lambda: mocks.acceso
    app.dependency_overrides[get_cargas_use_case] = lambda: mocks.cargas
    app.dependency_overrides[get_caracterizacion_use_case] = lambda: mocks.caracterizacion
    app.dependency_overrides[get_atribucion_use_case] = lambda: mocks.atribucion
    app.dependency_overrides[get_db_session] = lambda: None
    return TestClient(app)


def test_control_carga_de_planta_asignada_se_modifica(org_con_asignacion_parcial):
    client = _cliente(org_con_asignacion_parcial)

    resp = client.patch("/api/v1/cargas/carga-a1", json={"nombre": "x"})

    assert resp.status_code == 200
    org_con_asignacion_parcial.cargas.actualizar_carga.assert_called_once()


def test_patch_carga_de_planta_no_asignada_404(org_con_asignacion_parcial):
    client = _cliente(org_con_asignacion_parcial)

    resp = client.patch("/api/v1/cargas/carga-a2", json={"nombre": "x"})

    assert resp.status_code == 404
    org_con_asignacion_parcial.cargas.actualizar_carga.assert_not_called()


def test_get_carga_por_id_de_planta_no_asignada_404(org_con_asignacion_parcial):
    client = _cliente(org_con_asignacion_parcial)

    resp = client.get("/api/v1/cargas/carga-a2")

    assert resp.status_code == 404


def test_alta_de_carga_en_planta_no_asignada_404(org_con_asignacion_parcial):
    client = _cliente(org_con_asignacion_parcial)

    resp = client.post("/api/v1/cargas", json={"nombre": "x", "dispositivo_id": "dispositivo-a2"})

    assert resp.status_code == 404
    org_con_asignacion_parcial.cargas.registrar_carga.assert_not_called()


def test_abrir_campana_en_planta_no_asignada_404(org_con_asignacion_parcial):
    client = _cliente(org_con_asignacion_parcial)

    resp = client.post(
        "/api/v1/cargas/campanas/activas",
        json={"dispositivo_id": "dispositivo-a2", "duracion_segundos": 120},
    )

    assert resp.status_code == 404
    org_con_asignacion_parcial.caracterizacion.iniciar_activa.assert_not_called()


def test_get_campana_de_planta_no_asignada_404(org_con_asignacion_parcial):
    client = _cliente(org_con_asignacion_parcial)

    resp = client.get("/api/v1/cargas/campanas/camp-a2")

    assert resp.status_code == 404


def test_corregir_intervalo_de_planta_no_asignada_404(org_con_asignacion_parcial):
    client = _cliente(org_con_asignacion_parcial)

    resp = client.patch("/api/v1/cargas/intervalos/2/corregir", json={"notas": "x"})

    assert resp.status_code == 404
    org_con_asignacion_parcial.atribucion.corregir_intervalo.assert_not_called()


def test_listar_sin_device_id_omite_cargas_de_planta_no_asignada(org_con_asignacion_parcial):
    client = _cliente(org_con_asignacion_parcial)

    resp = client.get("/api/v1/cargas")

    assert resp.status_code == 200
    ids = [carga["id"] for carga in resp.json()]
    assert ids == ["carga-a1"]
