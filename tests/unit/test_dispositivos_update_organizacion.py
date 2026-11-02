"""tests/unit/test_dispositivos_update_organizacion.py — datamaq#118.

PUT y PATCH /dispositivos/{device_id} solo pueden modificar dispositivos de la organización de quien llama,
y la planta de destino tiene que ser de esa misma organización. Mismo criterio que el realtime (#99) y que
la lectura (`obtener_dispositivo_de_organizacion`). Un dispositivo ajeno responde 404, como uno inexistente.
"""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.dtos.dispositivo_dto import DispositivoUpdateDTO
from src.application.use_cases.gestionar_dispositivos import GestionarDispositivosUseCase
from src.domain.telemetria.entities import Dispositivo
from src.domain.telemetria.exceptions import DispositivoNoEncontradoError, PlantaNoEncontradaError
from src.domain.telemetria.value_objects import MacAddress
from src.infrastructure.fastapi.auth_dependencies import get_acceso_plantas_use_case
from src.infrastructure.fastapi.dependencies import get_registrar_auditoria_use_case, get_usuario_actual
from src.infrastructure.fastapi.device_ownership import verificar_propiedad_dispositivo
from src.infrastructure.fastapi.routes import dispositivos_router as router_mod

ORG_A = "org-a"
ORG_B = "org-b"
ID_A = "disp-a"
ID_B = "disp-b"
UID_A = "AA:BB:CC:00:00:01"
UID_B = "AA:BB:CC:00:00:02"
PLANTA_A = "planta-a"
PLANTA_A2 = "planta-a2"
PLANTA_B = "planta-b"

ORG_DE_PLANTA = {PLANTA_A: ORG_A, PLANTA_A2: ORG_A, PLANTA_B: ORG_B}


class _Planta:
    def __init__(self, id_: str, organizacion_id: str) -> None:
        self.id = id_
        self.organizacion_id = organizacion_id


class _RepoDispositivos:
    def __init__(self) -> None:
        self.disp = {
            ID_A: Dispositivo(id=ID_A, device_uid=MacAddress(UID_A), nombre="A", planta_id=PLANTA_A),
            ID_B: Dispositivo(id=ID_B, device_uid=MacAddress(UID_B), nombre="B", planta_id=PLANTA_B),
        }
        self.guardados: list[str] = []

    def obtener_por_id(self, dispositivo_id):
        return self.disp.get(dispositivo_id)

    def obtener_por_uid(self, uid):
        return next((d for d in self.disp.values() if d.device_uid.valor == uid.valor), None)

    def listar(self, planta_id=None, organizacion_id=None):
        return [
            d
            for d in self.disp.values()
            if organizacion_id is None or ORG_DE_PLANTA.get(d.planta_id) == organizacion_id
        ]

    def guardar(self, dispositivo):
        self.guardados.append(dispositivo.id)
        return dispositivo

    def actualizar_heartbeat(self, *args, **kwargs):
        return None


class _RepoOrganizaciones:
    def obtener_planta_por_id(self, planta_id):
        if planta_id not in ORG_DE_PLANTA:
            return None
        return _Planta(planta_id, ORG_DE_PLANTA[planta_id])

    def obtener_por_id(self, organizacion_id):
        return None

    def obtener_instalacion_medidor(self, dispositivo_id):
        return None

    def obtener_nodos_unifilar(self, planta_id):
        return []

    def obtener_dispositivos_layout(self, planta_id):
        return []


def _use_case(repo: _RepoDispositivos | None = None) -> GestionarDispositivosUseCase:
    return GestionarDispositivosUseCase(
        repo_dispositivos=repo or _RepoDispositivos(), repo_organizaciones=_RepoOrganizaciones()
    )


# --- Caso de uso ---------------------------------------------------------------------------------


@pytest.mark.parametrize("referencia", [ID_B, UID_B])
def test_no_actualiza_dispositivo_de_otra_organizacion(referencia):
    repo = _RepoDispositivos()
    with pytest.raises(DispositivoNoEncontradoError):
        _use_case(repo).actualizar_dispositivo_de_organizacion(
            referencia, DispositivoUpdateDTO(nombre="hackeado"), organizacion_id=ORG_A
        )
    assert repo.guardados == []
    assert repo.disp[ID_B].nombre == "B"


def test_actualiza_dispositivo_de_la_propia_organizacion():
    repo = _RepoDispositivos()
    res = _use_case(repo).actualizar_dispositivo_de_organizacion(
        ID_A, DispositivoUpdateDTO(nombre="nuevo"), organizacion_id=ORG_A
    )
    assert res.nombre == "nuevo"
    assert repo.guardados == [ID_A]


def test_no_mueve_a_planta_de_otra_organizacion():
    repo = _RepoDispositivos()
    with pytest.raises(PlantaNoEncontradaError):
        _use_case(repo).actualizar_dispositivo_de_organizacion(
            ID_A, DispositivoUpdateDTO(planta_id=PLANTA_B), organizacion_id=ORG_A
        )
    assert repo.guardados == []
    assert repo.disp[ID_A].planta_id == PLANTA_A


def test_mueve_a_planta_de_la_propia_organizacion():
    repo = _RepoDispositivos()
    res = _use_case(repo).actualizar_dispositivo_de_organizacion(
        ID_A, DispositivoUpdateDTO(planta_id=PLANTA_A2), organizacion_id=ORG_A
    )
    assert res.id == ID_A
    assert repo.guardados == [ID_A]


def test_superadmin_actualiza_dispositivo_de_cualquier_organizacion():
    repo = _RepoDispositivos()
    res = _use_case(repo).actualizar_dispositivo_de_organizacion(
        ID_B, DispositivoUpdateDTO(nombre="rootmod"), organizacion_id=None, es_superadmin=True
    )
    assert res.nombre == "rootmod"


# --- Ruta: operador de A sobre medidor de B ------------------------------------------------------


def _app(claims: dict, monkeypatch) -> FastAPI:
    app = FastAPI()
    app.include_router(router_mod.router)
    app.dependency_overrides[get_usuario_actual] = lambda: claims
    app.dependency_overrides[get_registrar_auditoria_use_case] = lambda: None
    # Este archivo prueba la regla de organización del caso de uso (#118); la propiedad por planta y la política de
    # plantas tienen su batería en test_edicion_dispositivo_por_planta.py (datamaq#133).
    app.dependency_overrides[verificar_propiedad_dispositivo] = lambda: None
    app.dependency_overrides[get_acceso_plantas_use_case] = lambda: MagicMock()
    repo = _RepoDispositivos()
    app.dependency_overrides[router_mod.get_dispositivos_use_case] = lambda: _use_case(repo)
    monkeypatch.setattr(router_mod, "get_mqtt_listener", lambda: MagicMock())
    return app


def _operador_a() -> dict:
    return {"sub": "op-a", "rol": "operador", "org": ORG_A}


@pytest.mark.parametrize("metodo", ["patch", "put"])
@pytest.mark.parametrize("referencia", [ID_B, UID_B])
def test_ruta_operador_de_a_recibe_404_sobre_medidor_de_b(monkeypatch, metodo, referencia):
    cliente = TestClient(_app(_operador_a(), monkeypatch))
    resp = getattr(cliente, metodo)(f"/api/v1/dispositivos/{referencia}", json={"nombre": "hackeado"})
    assert resp.status_code == 404


def test_ruta_operador_de_a_puede_editar_su_medidor(monkeypatch):
    cliente = TestClient(_app(_operador_a(), monkeypatch))
    resp = cliente.patch(f"/api/v1/dispositivos/{ID_A}", json={"nombre": "nuevo"})
    assert resp.status_code == 200
    assert resp.json()["nombre"] == "nuevo"


def test_ruta_operador_de_a_recibe_404_al_mover_a_planta_de_b(monkeypatch):
    cliente = TestClient(_app(_operador_a(), monkeypatch))
    resp = cliente.patch(f"/api/v1/dispositivos/{ID_A}", json={"planta_id": PLANTA_B})
    assert resp.status_code == 404
