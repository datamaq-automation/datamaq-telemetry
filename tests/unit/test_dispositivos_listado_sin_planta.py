"""tests/unit/test_dispositivos_listado_sin_planta.py — Issue datamaq#125: el listado no confunde "ninguna planta" con "todas".

`resolver_planta_permitida` devuelve None cuando el usuario no tiene ninguna planta permitida (fail-close, #85).
`listar(planta_id=None)` de un repositorio de dispositivos significa "todas las plantas". El listado de
/api/v1/dispositivos pasaba de uno al otro y devolvía todos los dispositivos de la organización a un usuario
restringido sin plantas válidas. Política real de acceso a plantas, caso de uso real de dispositivos y un
repositorio espía: si el listado le pide algo a la base, el espía lo registra.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.application.use_cases.gestionar_acceso_plantas import GestionarAccesoPlantasUseCase
from src.application.use_cases.gestionar_dispositivos import GestionarDispositivosUseCase
from src.domain.auth.entities import AccesoPlantaUsuario
from src.domain.telemetria.entities import Planta
from src.infrastructure.fastapi.auth_dependencies import get_acceso_plantas_use_case
from src.infrastructure.fastapi.dependencies import get_dispositivos_use_case, get_usuario_actual
from src.infrastructure.fastapi.server import create_app

PLANTAS = [
    Planta(id="a1", organizacion_id="org-a", nombre="A1"),
    Planta(id="a2", organizacion_id="org-a", nombre="A2"),
    Planta(id="b1", organizacion_id="org-b", nombre="B1"),
]
USUARIO_A = {"sub": "u-a", "rol": "operador", "org": "org-a"}


def _acceso(planta_id: str) -> AccesoPlantaUsuario:
    return AccesoPlantaUsuario(usuario_id="u-a", planta_id=planta_id, puede_cambiar=False)


@pytest.fixture
def cliente(monkeypatch):
    """Fábrica de (cliente, repositorio espía de dispositivos) por claims y filas de user_facility_access."""
    monkeypatch.setattr(
        "src.infrastructure.fastapi.planta_ownership.get_settings", lambda: MagicMock(AUTH_REQUIRED=True)
    )

    def _crear(claims: dict, accesos: list[AccesoPlantaUsuario]) -> tuple[TestClient, MagicMock]:
        repo_accesos = MagicMock()
        repo_accesos.listar_por_usuario.return_value = accesos
        repo_org = MagicMock()
        repo_org.listar_plantas.side_effect = lambda org=None: [
            p for p in PLANTAS if org is None or p.organizacion_id == org
        ]
        repo_dispositivos = MagicMock()
        repo_dispositivos.listar.return_value = []
        app = create_app()
        app.dependency_overrides[get_usuario_actual] = lambda: claims
        app.dependency_overrides[get_acceso_plantas_use_case] = lambda: GestionarAccesoPlantasUseCase(
            repo_accesos, repo_org
        )
        app.dependency_overrides[get_dispositivos_use_case] = lambda: GestionarDispositivosUseCase(
            repo_dispositivos, repo_org
        )
        return TestClient(app), repo_dispositivos

    return _crear


@pytest.mark.parametrize(
    "accesos",
    [
        pytest.param([_acceso("p-eliminada")], id="planta_que_ya_no_existe_en_el_yaml"),
        pytest.param([_acceso("b1")], id="planta_de_otra_organizacion"),
    ],
)
def test_sin_plantas_permitidas_el_listado_es_vacio_y_no_consulta_dispositivos(cliente, accesos):
    client, repo_dispositivos = cliente(USUARIO_A, accesos)

    response = client.get("/api/v1/dispositivos")

    assert response.status_code == 200
    assert response.json() == []
    repo_dispositivos.listar.assert_not_called()


def test_usuario_con_una_planta_ve_solo_esa_planta(cliente):
    client, repo_dispositivos = cliente(USUARIO_A, [_acceso("a1")])

    response = client.get("/api/v1/dispositivos")

    assert response.status_code == 200
    repo_dispositivos.listar.assert_called_once_with("a1", organizacion_id="org-a")


def test_pedir_una_planta_no_asignada_sigue_siendo_404_sin_consultar_dispositivos(cliente):
    client, repo_dispositivos = cliente(USUARIO_A, [_acceso("a1")])

    response = client.get("/api/v1/dispositivos?planta_id=a2")

    assert response.status_code == 404
    repo_dispositivos.listar.assert_not_called()


def test_superadmin_no_se_acota_por_organizacion(cliente):
    client, repo_dispositivos = cliente({"sub": "root", "rol": "superadmin"}, [])

    response = client.get("/api/v1/dispositivos")

    assert response.status_code == 200
    repo_dispositivos.listar.assert_called_once()
    assert repo_dispositivos.listar.call_args.kwargs["organizacion_id"] is None
