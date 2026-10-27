"""tests/unit/test_seguridad_facility_access.py — Aislamiento por facility/planta dentro de la misma organización (#51)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.application.dtos.organizacion_dto import PlantaResponseDTO
from src.application.use_cases.gestionar_acceso_plantas import GestionarAccesoPlantasUseCase
from src.domain.auth.entities import AccesoPlantaUsuario
from src.domain.auth.ports import RepositorioAccesosPlantaPort
from src.domain.telemetria.entities import Planta
from src.infrastructure.fastapi.auth_dependencies import get_acceso_plantas_use_case
from src.infrastructure.fastapi.dependencies import (
    get_alertas_use_case,
    get_dispositivos_use_case,
    get_telemetria_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.device_ownership import verificar_propiedad_dispositivo
from src.infrastructure.fastapi.server import create_app

PLANTAS = [
    Planta(id="a1", organizacion_id="org-a", nombre="Planta A1"),
    Planta(id="a2", organizacion_id="org-a", nombre="Planta A2"),
    Planta(id="b1", organizacion_id="org-b", nombre="Planta B1"),
]

USUARIO_A = {"sub": "u-a", "rol": "operador", "org": "org-a"}


class RepoAccesosEnMemoria(RepositorioAccesosPlantaPort):
    def __init__(self, accesos: list[AccesoPlantaUsuario]):
        self.accesos = accesos

    def listar_por_usuario(self, usuario_id: str) -> list[AccesoPlantaUsuario]:
        return [a for a in self.accesos if a.usuario_id == usuario_id]

    def reemplazar(self, usuario_id: str, accesos: list[AccesoPlantaUsuario]) -> list[AccesoPlantaUsuario]:
        raise NotImplementedError


def _repo_org() -> MagicMock:
    repo = MagicMock()
    repo.listar_plantas.side_effect = lambda org=None: [p for p in PLANTAS if org is None or p.organizacion_id == org]
    repo.obtener_planta_por_id.side_effect = lambda pid: next((p for p in PLANTAS if p.id == pid), None)
    return repo


class _FakeDispositivo:
    def __init__(self, planta_id: str | None) -> None:
        self.planta_id = planta_id


class _FakePlanta:
    def __init__(self, organizacion_id: str | None) -> None:
        self.organizacion_id = organizacion_id


class _FakeSettings:
    def __init__(self, auth_required: bool = True) -> None:
        self.AUTH_REQUIRED = auth_required


def _mock_mysql_repos(monkeypatch, repo_dispositivos=None, repo_organizaciones=None):
    monkeypatch.setattr(
        "src.infrastructure.fastapi.device_ownership.repo_dispositivos_resuelto",
        lambda db: repo_dispositivos or MagicMock(),
    )
    monkeypatch.setattr(
        "src.infrastructure.fastapi.device_ownership.YamlOrganizacionesRepository",
        lambda *args, **kwargs: repo_organizaciones or MagicMock(),
    )


def test_verificar_propiedad_dispositivo_rechaza_planta_no_asignada_de_misma_org(monkeypatch):
    """Un usuario con acceso asignado solo a a1 no puede acceder a un dispositivo de a2 (misma org-a)."""
    repo_dispositivos = MagicMock()
    repo_dispositivos.obtener_por_id.return_value = _FakeDispositivo(planta_id="a2")
    repo_organizaciones = _repo_org()
    _mock_mysql_repos(monkeypatch, repo_dispositivos, repo_organizaciones)

    acceso_plantas = GestionarAccesoPlantasUseCase(
        RepoAccesosEnMemoria([AccesoPlantaUsuario("u-a", "a1", puede_cambiar=False)]),
        repo_organizaciones,
    )

    with patch(
        "src.infrastructure.fastapi.device_ownership.get_settings",
        return_value=_FakeSettings(auth_required=True),
    ):
        with pytest.raises(HTTPException) as exc_info:
            verificar_propiedad_dispositivo(
                claims=USUARIO_A,
                db=MagicMock(),
                acceso_plantas=acceso_plantas,
                device_id="dev-a2",
            )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "dispositivo_no_encontrado"


def test_verificar_propiedad_dispositivo_permite_planta_asignada(monkeypatch):
    """Un usuario con acceso asignado a a1 puede acceder a un dispositivo de a1."""
    repo_dispositivos = MagicMock()
    repo_dispositivos.obtener_por_id.return_value = _FakeDispositivo(planta_id="a1")
    repo_organizaciones = _repo_org()
    _mock_mysql_repos(monkeypatch, repo_dispositivos, repo_organizaciones)

    acceso_plantas = GestionarAccesoPlantasUseCase(
        RepoAccesosEnMemoria([AccesoPlantaUsuario("u-a", "a1", puede_cambiar=False)]),
        repo_organizaciones,
    )

    with patch(
        "src.infrastructure.fastapi.device_ownership.get_settings",
        return_value=_FakeSettings(auth_required=True),
    ):
        verificar_propiedad_dispositivo(
            claims=USUARIO_A,
            db=MagicMock(),
            acceso_plantas=acceso_plantas,
            device_id="dev-a1",
        )


def test_listar_plantas_filtra_por_user_facility_access():
    """GET /api/v1/plantas solo devuelve las plantas asignadas al usuario dentro de su org."""
    app = create_app()
    repo_org = _repo_org()
    acceso = GestionarAccesoPlantasUseCase(
        RepoAccesosEnMemoria([AccesoPlantaUsuario("u-a", "a1", puede_cambiar=False)]),
        repo_org,
    )
    mock_dispositivos_uc = MagicMock()
    ahora = datetime.now(timezone.utc)
    mock_dispositivos_uc.listar_plantas.return_value = [
        PlantaResponseDTO(
            id="a1",
            nombre="Planta A1",
            slug="planta-a1",
            organizacion_id="org-a",
            creado_en=ahora,
            actualizado_en=ahora,
        ),
        PlantaResponseDTO(
            id="a2",
            nombre="Planta A2",
            slug="planta-a2",
            organizacion_id="org-a",
            creado_en=ahora,
            actualizado_en=ahora,
        ),
    ]

    app.dependency_overrides[get_usuario_actual] = lambda: USUARIO_A
    app.dependency_overrides[get_acceso_plantas_use_case] = lambda: acceso
    app.dependency_overrides[get_dispositivos_use_case] = lambda: mock_dispositivos_uc

    client = TestClient(app)
    response = client.get("/api/v1/plantas")
    assert response.status_code == 200
    ids = [p["id"] for p in response.json()]
    assert ids == ["a1"]


def test_alertas_con_planta_id_rechaza_planta_no_asignada():
    """GET /api/v1/alertas?planta_id=a2 rechaza con 404 si a2 no está asignada al usuario."""
    app = create_app()
    repo_org = _repo_org()
    acceso = GestionarAccesoPlantasUseCase(
        RepoAccesosEnMemoria([AccesoPlantaUsuario("u-a", "a1", puede_cambiar=False)]),
        repo_org,
    )
    mock_alertas_uc = MagicMock()

    app.dependency_overrides[get_usuario_actual] = lambda: USUARIO_A
    app.dependency_overrides[get_acceso_plantas_use_case] = lambda: acceso
    app.dependency_overrides[get_alertas_use_case] = lambda: mock_alertas_uc

    client = TestClient(app)
    response = client.get("/api/v1/alertas?planta_id=a2")
    assert response.status_code == 404
    assert response.json()["detail"] == "planta_no_encontrada"


def test_instantaneous_rechaza_dispositivo_de_planta_no_asignada(monkeypatch):
    """GET /api/v1/telemetria/instantaneous/{id} rechaza con 404 si el dispositivo es de planta no asignada."""
    app = create_app()
    repo_dispositivos = MagicMock()
    repo_dispositivos.obtener_por_id.return_value = _FakeDispositivo(planta_id="a2")
    repo_org = _repo_org()
    _mock_mysql_repos(monkeypatch, repo_dispositivos, repo_org)

    acceso = GestionarAccesoPlantasUseCase(
        RepoAccesosEnMemoria([AccesoPlantaUsuario("u-a", "a1", puede_cambiar=False)]),
        repo_org,
    )
    mock_telemetria_uc = MagicMock()

    app.dependency_overrides[get_usuario_actual] = lambda: USUARIO_A
    app.dependency_overrides[get_acceso_plantas_use_case] = lambda: acceso
    app.dependency_overrides[get_telemetria_use_case] = lambda: mock_telemetria_uc

    monkeypatch.setattr(
        "src.infrastructure.fastapi.device_ownership.get_settings",
        lambda: MagicMock(AUTH_REQUIRED=True),
    )

    client = TestClient(app)
    response = client.get("/api/v1/telemetria/instantaneous/dev-a2")
    assert response.status_code == 404
    assert response.json()["detail"] == "dispositivo_no_encontrado"


def test_instantaneous_permite_dispositivo_de_planta_asignada(monkeypatch):
    """GET /api/v1/telemetria/instantaneous/{id} permite 200 si el dispositivo es de planta asignada."""
    app = create_app()
    repo_dispositivos = MagicMock()
    repo_dispositivos.obtener_por_id.return_value = _FakeDispositivo(planta_id="a1")
    repo_org = _repo_org()
    _mock_mysql_repos(monkeypatch, repo_dispositivos, repo_org)

    acceso = GestionarAccesoPlantasUseCase(
        RepoAccesosEnMemoria([AccesoPlantaUsuario("u-a", "a1", puede_cambiar=False)]),
        repo_org,
    )
    mock_telemetria_uc = MagicMock()
    mock_telemetria_uc.historico_instantaneas.return_value = MagicMock(
        lecturas=[], datos_desde=datetime.now(timezone.utc)
    )
    mock_telemetria_uc.potencia_referencia.return_value = None

    app.dependency_overrides[get_usuario_actual] = lambda: USUARIO_A
    app.dependency_overrides[get_acceso_plantas_use_case] = lambda: acceso
    app.dependency_overrides[get_telemetria_use_case] = lambda: mock_telemetria_uc

    monkeypatch.setattr(
        "src.infrastructure.fastapi.device_ownership.get_settings",
        lambda: MagicMock(AUTH_REQUIRED=True),
    )

    client = TestClient(app)
    response = client.get("/api/v1/telemetria/instantaneous/dev-a1")
    assert response.status_code == 200
