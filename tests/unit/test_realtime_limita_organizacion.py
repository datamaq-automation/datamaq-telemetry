"""tests/unit/test_realtime_limita_organizacion.py — El realtime solo activa dispositivos de la organización del usuario (#99).

Misma regla que el listado: superadmin sin filtro; el resto, solo dentro de su organización. Un dispositivo de otra
organización responde 404, igual que uno inexistente. La búsqueda por id y por UID pasan por la misma comprobación.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.use_cases.gestionar_dispositivos import GestionarDispositivosUseCase
from src.domain.telemetria.entities import Dispositivo
from src.domain.telemetria.value_objects import MacAddress
from src.infrastructure.auth.jwt_token_service import JwtTokenService
from src.infrastructure.fastapi import routes as _routes  # noqa: F401  (carga el paquete)
from src.infrastructure.fastapi.dependencies import get_usuario_actual
from src.infrastructure.fastapi.middleware import registrar_guard_solo_lectura
from src.infrastructure.fastapi.routes import dispositivos_router as router_mod

ORG_A = "org-a"
ORG_B = "org-b"
ID_A = "disp-a"
ID_B = "disp-b"
UID_A = "AA:BB:CC:00:00:01"
UID_B = "AA:BB:CC:00:00:02"
SECRETO = "clave-de-prueba-larga-0123456789abcdef"


class _RepoDispositivos:
    """Repositorio falso: cada dispositivo pertenece a una organización, como el join con facilities."""

    def __init__(self) -> None:
        self.disp = {
            ID_A: Dispositivo(id=ID_A, device_uid=MacAddress(UID_A), nombre="A", planta_id="planta-a"),
            ID_B: Dispositivo(id=ID_B, device_uid=MacAddress(UID_B), nombre="B", planta_id="planta-b"),
        }
        self.org_de = {ID_A: ORG_A, ID_B: ORG_B}

    def obtener_por_id(self, dispositivo_id):
        return self.disp.get(dispositivo_id)

    def obtener_por_uid(self, uid):
        return next((d for d in self.disp.values() if d.device_uid.valor == uid.valor), None)

    def listar(self, planta_id=None, organizacion_id=None):
        return [d for d in self.disp.values() if organizacion_id is None or self.org_de[d.id] == organizacion_id]


def _use_case() -> GestionarDispositivosUseCase:
    return GestionarDispositivosUseCase(repo_dispositivos=_RepoDispositivos(), repo_organizaciones=MagicMock())


def _app(claims: dict, monkeypatch) -> FastAPI:
    app = FastAPI()
    app.include_router(router_mod.router)
    app.dependency_overrides[get_usuario_actual] = lambda: claims
    app.dependency_overrides[router_mod.get_dispositivos_use_case] = lambda: _use_case()
    listener = MagicMock()
    listener.activar_tiempo_real_dispositivo.return_value = True
    monkeypatch.setattr(router_mod, "get_mqtt_listener", lambda: listener)
    return app


def _operador_a() -> dict:
    return {"sub": "op-a", "rol": "operador", "org": ORG_A}


# --- Caso de uso: id y UID pasan por el mismo filtro -------------------------------------------------


@pytest.mark.parametrize("referencia", [ID_A, UID_A])
def test_caso_de_uso_acepta_dispositivo_de_la_propia_organizacion(referencia):
    dto = _use_case().obtener_dispositivo_de_organizacion(referencia, ORG_A)
    assert dto.id == ID_A


@pytest.mark.parametrize("referencia", [ID_B, UID_B])
def test_caso_de_uso_rechaza_dispositivo_de_otra_organizacion_por_id_y_por_uid(referencia):
    from src.domain.telemetria.exceptions import DispositivoNoEncontradoError

    with pytest.raises(DispositivoNoEncontradoError):
        _use_case().obtener_dispositivo_de_organizacion(referencia, ORG_A)


def test_sin_organizacion_en_el_claim_responde_como_inexistente():
    from src.domain.telemetria.exceptions import DispositivoNoEncontradoError

    with pytest.raises(DispositivoNoEncontradoError):
        _use_case().obtener_dispositivo_de_organizacion(ID_A, None)


# --- Ruta: 200 / 404 / 401 / 403 ---------------------------------------------------------------------


def test_operador_de_a_activa_dispositivo_de_a(monkeypatch):
    cliente = TestClient(_app(_operador_a(), monkeypatch))
    assert cliente.post(f"/api/v1/dispositivos/{ID_A}/realtime").status_code == 200


@pytest.mark.parametrize("referencia", [ID_B, UID_B])
def test_operador_de_a_recibe_404_sobre_dispositivo_de_b_por_id_y_uid(monkeypatch, referencia):
    cliente = TestClient(_app(_operador_a(), monkeypatch))
    assert cliente.post(f"/api/v1/dispositivos/{referencia}/realtime").status_code == 404


def test_superadmin_activa_dispositivo_de_b(monkeypatch):
    cliente = TestClient(_app({"sub": "root", "rol": "superadmin"}, monkeypatch))
    assert cliente.post(f"/api/v1/dispositivos/{ID_B}/realtime").status_code == 200


def test_sin_token_responde_401_con_la_autenticacion_de_siempre():
    # Sin el override, get_usuario_actual exige token: la ruta no cambia esa regla.
    app = FastAPI()
    app.include_router(router_mod.router)
    app.dependency_overrides[router_mod.get_dispositivos_use_case] = lambda: _use_case()
    assert TestClient(app).post(f"/api/v1/dispositivos/{ID_A}/realtime").status_code == 401


def test_solo_lectura_recibe_403_por_el_middleware(monkeypatch):
    app = _app({"sub": "lector", "rol": "solo_lectura", "org": ORG_A}, monkeypatch)
    registrar_guard_solo_lectura(
        app,
        MagicMock(
            API_SOLO_LECTURA=False,
            API_SOLO_LECTURA_EXCEPCIONES="",
            DB_NAME="datamaq_telemetry",
            API_SECRET_KEY=SECRETO,
            API_SECRET_KEY_ANTERIOR="",
            AUTH_COOKIE_NOMBRE="datamaq_token",
        ),
    )
    # Token firmado de verdad: el middleware verifica la firma y lee el rol.
    token = JwtTokenService(SECRETO).generar(
        "lector", "lector", datetime.now(timezone.utc) + timedelta(hours=1), rol="solo_lectura", organizacion_id=ORG_A
    )
    cliente = TestClient(app)
    assert (
        cliente.post(f"/api/v1/dispositivos/{ID_A}/realtime", headers={"Authorization": f"Bearer {token}"}).status_code
        == 403
    )
