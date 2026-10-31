"""tests/unit/test_cargas_escrituras_organizacion.py — Las escrituras de cargas respetan la organización (#42).

Dos organizaciones (A y B), cada una con un medidor. Un operador de A no modifica cargas, campañas,
intervalos ni registra cargas en el medidor de B: 404, como las lecturas de #41. El superadmin sí.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.application.dtos.carga_dto import CampanaResponseDTO, CargaResponseDTO, IntervaloActividadResponseDTO
from src.application.use_cases.gestionar_acceso_plantas import GestionarAccesoPlantasUseCase
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

    cargas = MagicMock()
    cargas.obtener_carga.side_effect = lambda carga_id: {
        "carga-a": _carga("carga-a", "dispositivo-a"),
        "carga-b": _carga("carga-b", "dispositivo-b"),
    }[carga_id]
    cargas.actualizar_carga.side_effect = lambda carga_id, _dto: _carga(carga_id, "dispositivo-b")
    cargas.fijar_firma_manual.side_effect = lambda carga_id, _dto: _carga(carga_id, "dispositivo-b")
    cargas.registrar_carga.side_effect = lambda dto: _carga("nueva", dto.dispositivo_id)

    caracterizacion = MagicMock()
    caracterizacion.obtener.side_effect = lambda campana_id: _campana(campana_id, "dispositivo-b")
    caracterizacion.iniciar_activa.side_effect = lambda dto, usuario_id=None: _campana("nueva", dto.dispositivo_id)
    caracterizacion.iniciar_pasiva.side_effect = lambda dto, usuario_id=None: _campana("nueva", dto.dispositivo_id)
    caracterizacion.finalizar.side_effect = lambda campana_id: _campana(campana_id, "dispositivo-b")
    caracterizacion.descartar.side_effect = lambda campana_id, motivo=None: _campana(campana_id, "dispositivo-b")

    atribucion = MagicMock()
    atribucion.dispositivo_de_intervalo.side_effect = lambda intervalo_id: {1: "dispositivo-b", 2: "dispositivo-a"}[
        intervalo_id
    ]
    atribucion.corregir_intervalo.side_effect = lambda intervalo_id, _dto, usuario_id=None: _intervalo(
        intervalo_id, "dispositivo-b"
    )

    return SimpleNamespace(cargas=cargas, caracterizacion=caracterizacion, atribucion=atribucion)


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


def _cliente(rol: str, org: str, mocks: SimpleNamespace) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_usuario_actual] = lambda: {"sub": "u-1", "rol": rol, "org": org}
    app.dependency_overrides[get_cargas_use_case] = lambda: mocks.cargas
    app.dependency_overrides[get_caracterizacion_use_case] = lambda: mocks.caracterizacion
    app.dependency_overrides[get_atribucion_use_case] = lambda: mocks.atribucion
    app.dependency_overrides[get_acceso_plantas_use_case] = _acceso_sin_asignaciones
    app.dependency_overrides[get_db_session] = lambda: None
    return TestClient(app)


# --- un contrato por escritura: el operador de A recibe 404 sobre el medidor de B ---


def test_patch_carga_de_b_no_se_modifica_desde_a(dos_organizaciones):
    client = _cliente("operador", "org-a", dos_organizaciones)

    resp = client.patch("/api/v1/cargas/carga-b", json={"nombre": "x"})

    assert resp.status_code == 404
    dos_organizaciones.cargas.actualizar_carga.assert_not_called()


def test_put_firma_de_carga_de_b_no_se_fija_desde_a(dos_organizaciones):
    client = _cliente("operador", "org-a", dos_organizaciones)

    resp = client.put("/api/v1/cargas/carga-b/firma", json={"potencia_w": 100.0})

    assert resp.status_code == 404
    dos_organizaciones.cargas.fijar_firma_manual.assert_not_called()


def test_registrar_carga_en_medidor_de_b_desde_a_404(dos_organizaciones):
    client = _cliente("operador", "org-a", dos_organizaciones)

    resp = client.post("/api/v1/cargas", json={"nombre": "x", "dispositivo_id": "dispositivo-b"})

    assert resp.status_code == 404
    dos_organizaciones.cargas.registrar_carga.assert_not_called()


@pytest.mark.parametrize("ruta", ["/api/v1/cargas/campanas/activas", "/api/v1/cargas/campanas/pasivas"])
def test_abrir_campana_en_medidor_de_b_desde_a_404(dos_organizaciones, ruta):
    client = _cliente("operador", "org-a", dos_organizaciones)

    resp = client.post(ruta, json={"dispositivo_id": "dispositivo-b", "duracion_segundos": 120})

    assert resp.status_code == 404
    dos_organizaciones.caracterizacion.iniciar_activa.assert_not_called()
    dos_organizaciones.caracterizacion.iniciar_pasiva.assert_not_called()


def test_abrir_campana_con_carga_de_b_desde_a_404(dos_organizaciones):
    client = _cliente("operador", "org-a", dos_organizaciones)

    resp = client.post(
        "/api/v1/cargas/campanas/activas",
        json={"dispositivo_id": "dispositivo-a", "duracion_segundos": 120, "carga_id": "carga-b"},
    )

    assert resp.status_code == 404
    dos_organizaciones.caracterizacion.iniciar_activa.assert_not_called()


@pytest.mark.parametrize("accion", ["finalizar", "descartar"])
def test_cerrar_campana_de_b_desde_a_404(dos_organizaciones, accion):
    client = _cliente("operador", "org-a", dos_organizaciones)

    resp = client.patch(f"/api/v1/cargas/campanas/camp-b/{accion}", params={"motivo": "x"})

    assert resp.status_code == 404
    dos_organizaciones.caracterizacion.finalizar.assert_not_called()
    dos_organizaciones.caracterizacion.descartar.assert_not_called()


def test_corregir_intervalo_de_b_desde_a_404(dos_organizaciones):
    client = _cliente("operador", "org-a", dos_organizaciones)

    resp = client.patch("/api/v1/cargas/intervalos/1/corregir", json={"notas": "x"})

    assert resp.status_code == 404
    dos_organizaciones.atribucion.corregir_intervalo.assert_not_called()


def test_reimputar_intervalo_de_a_a_una_carga_de_b_desde_a_404(dos_organizaciones):
    client = _cliente("operador", "org-a", dos_organizaciones)

    resp = client.patch("/api/v1/cargas/intervalos/2/corregir", json={"carga_id": "carga-b"})

    assert resp.status_code == 404
    dos_organizaciones.atribucion.corregir_intervalo.assert_not_called()


# --- el superadmin mantiene el acceso global ---


def test_superadmin_modifica_carga_de_b(dos_organizaciones):
    client = _cliente("superadmin", "org-a", dos_organizaciones)

    resp = client.patch("/api/v1/cargas/carga-b", json={"nombre": "nuevo"})

    assert resp.status_code == 200
    dos_organizaciones.cargas.actualizar_carga.assert_called_once()


def test_superadmin_corrige_intervalo_de_b(dos_organizaciones):
    client = _cliente("superadmin", "org-a", dos_organizaciones)

    resp = client.patch("/api/v1/cargas/intervalos/1/corregir", json={"notas": "x"})

    assert resp.status_code == 200
    dos_organizaciones.atribucion.corregir_intervalo.assert_called_once()
