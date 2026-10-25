"""tests/unit/test_aislamiento_planta_api.py — Aislamiento por planta en las rutas que reciben `planta_id` (IDOR).

Política real (`GestionarAccesoPlantasUseCase` + `PoliticaAccesoPlantasService`) con repos en memoria:
org A tiene `a1` y `a2`; org B tiene `b1`.
"""

from collections.abc import Callable
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.application.use_cases.gestionar_acceso_plantas import GestionarAccesoPlantasUseCase
from src.application.use_cases.gestionar_planta_estructura import GestionarPlantaEstructuraUseCase
from src.domain.auth.entities import AccesoPlantaUsuario
from src.domain.auth.ports import RepositorioAccesosPlantaPort
from src.domain.telemetria.entities import Planta
from src.infrastructure.fastapi.auth_dependencies import get_acceso_plantas_use_case
from src.infrastructure.fastapi.dependencies import (
    get_consultar_analitica_planta_use_case,
    get_consultar_nodo_unifilar_use_case,
    get_planta_estructura_use_case,
    get_usuario_actual,
)
from src.infrastructure.fastapi.routes.sge_router import (
    get_consultar_ahorros_use_case,
    get_consultar_balance_use_case,
    get_organizaciones_repository,
)
from src.infrastructure.fastapi.server import create_app

PLANTAS = [
    Planta(id="a1", organizacion_id="org-a", nombre="A1"),
    Planta(id="a2", organizacion_id="org-a", nombre="A2"),
    Planta(id="b1", organizacion_id="org-b", nombre="B1"),
]

RUTAS_POR_PLANTA = [
    "/api/v1/plantas/{p}/unifilar",
    "/api/v1/plantas/{p}/areas",
    "/api/v1/plantas/{p}/layout",
    "/api/v1/plantas/{p}/unifilar/nodos/n1/resumen",
    "/api/v1/plantas/{p}/unifilar/nodos/n1/resumen/historico",
    "/api/v1/sge/plantas/{p}/balance-energia",
    "/api/v1/sge/plantas/{p}/ahorros-cusum?unidades_producidas=1&horas_periodo=1&energia_real_kwh=1",
    "/api/v1/sge/plantas/{p}/linea-base",
    "/api/v1/analitica/banco-capacitores/planta?planta_id={p}",
    "/api/v1/analitica/penalizaciones/planta?planta_id={p}",
    "/api/v1/planta/unifilar?planta_id={p}",
    "/api/v1/planta/areas?planta_id={p}",
    "/api/v1/planta/layout?planta_id={p}",
]


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
    repo.obtener_nodos_unifilar.return_value = []
    repo.obtener_zonas_planta.return_value = []
    repo.obtener_dispositivos_layout.return_value = []
    return repo


@pytest.fixture
def cliente(monkeypatch) -> tuple[Callable[..., TestClient], MagicMock]:
    """Fábrica de clientes por claims. Los casos de uso aguas abajo de la verificación son mocks:
    si la verificación deja pasar una planta ajena, el mock se llama y el test lo detecta."""
    monkeypatch.setattr(
        "src.infrastructure.fastapi.planta_ownership.get_settings", lambda: MagicMock(AUTH_REQUIRED=True)
    )
    aguas_abajo = MagicMock()

    def _crear(claims: dict, accesos: list[AccesoPlantaUsuario] | None = None) -> TestClient:
        app = create_app()
        repo_org = _repo_org()
        acceso = GestionarAccesoPlantasUseCase(RepoAccesosEnMemoria(accesos or []), repo_org)
        app.dependency_overrides[get_usuario_actual] = lambda: claims
        app.dependency_overrides[get_acceso_plantas_use_case] = lambda: acceso
        app.dependency_overrides[get_planta_estructura_use_case] = lambda: GestionarPlantaEstructuraUseCase(repo_org)
        for dep in (
            get_consultar_nodo_unifilar_use_case,
            get_consultar_balance_use_case,
            get_consultar_ahorros_use_case,
            get_organizaciones_repository,
            get_consultar_analitica_planta_use_case,
        ):
            app.dependency_overrides[dep] = lambda: aguas_abajo
        return TestClient(app)

    return _crear, aguas_abajo


USUARIO_A = {"sub": "u-a", "rol": "operador", "org": "org-a"}


@pytest.mark.parametrize("ruta", RUTAS_POR_PLANTA)
def test_usuario_de_otra_organizacion_recibe_404(cliente, ruta):
    crear, aguas_abajo = cliente
    response = crear(USUARIO_A).get(ruta.format(p="b1"))
    assert response.status_code == 404
    assert response.json()["detail"] == "planta_no_encontrada"
    assert aguas_abajo.mock_calls == []


@pytest.mark.parametrize("ruta", RUTAS_POR_PLANTA)
def test_planta_inexistente_responde_igual_que_la_ajena(cliente, ruta):
    crear, _ = cliente
    response = crear(USUARIO_A).get(ruta.format(p="no-existe"))
    assert response.status_code == 404
    assert response.json()["detail"] == "planta_no_encontrada"


def test_usuario_con_asignaciones_recibe_404_en_planta_no_asignada_de_su_org(cliente):
    crear, _ = cliente
    client = crear(USUARIO_A, [AccesoPlantaUsuario("u-a", "a1", puede_cambiar=False)])
    assert client.get("/api/v1/plantas/a2/unifilar").status_code == 404
    assert client.get("/api/v1/planta/unifilar?planta_id=a2").status_code == 404
    assert client.get("/api/v1/plantas/a1/unifilar").status_code == 200


def test_planta_activa_por_defecto_es_la_de_la_politica(cliente):
    """Sin planta_id: la primera permitida (igual a planta_activa_id de /auth/me), no la primera de la org."""
    crear, _ = cliente
    client = crear(USUARIO_A, [AccesoPlantaUsuario("u-a", "a2", puede_cambiar=False)])
    assert client.get("/api/v1/planta/unifilar").json()["planta_id"] == "a2"
    assert client.get("/api/v1/planta/layout").json()["planta_id"] == "a2"
    assert client.get("/api/v1/planta/areas").json()["planta_id"] == "a2"


def test_usuario_sin_organizacion_no_recibe_planta_por_defecto(cliente):
    crear, _ = cliente
    response = crear({"sub": "u-x", "rol": "operador"}).get("/api/v1/planta/unifilar")
    assert response.status_code == 200
    assert response.json()["planta_id"] == ""


def test_usuario_propio_accede_a_su_planta(cliente):
    crear, _ = cliente
    client = crear(USUARIO_A)
    assert client.get("/api/v1/plantas/a2/unifilar").json()["planta_id"] == "a2"
    assert client.get("/api/v1/planta/unifilar?planta_id=a2").json()["planta_id"] == "a2"


@pytest.mark.parametrize("rol", ["superadmin"])
def test_roles_globales_acceden_a_cualquier_planta(cliente, rol):
    crear, _ = cliente
    client = crear({"sub": "u-g", "rol": rol, "org": "org-a"})
    for ruta in ("/api/v1/plantas/b1/unifilar", "/api/v1/plantas/b1/areas", "/api/v1/plantas/b1/layout"):
        response = client.get(ruta)
        assert response.status_code == 200
        assert response.json()["planta_id"] == "b1"


def test_sin_auth_requerida_se_resuelve_como_rol_global(cliente, monkeypatch):
    crear, _ = cliente
    monkeypatch.setattr(
        "src.infrastructure.fastapi.planta_ownership.get_settings", lambda: MagicMock(AUTH_REQUIRED=False)
    )
    client = crear({"sub": "anon", "rol": "admin"})
    assert client.get("/api/v1/plantas/b1/unifilar").json()["planta_id"] == "b1"
    assert client.get("/api/v1/planta/unifilar").json()["planta_id"] == "a1"
