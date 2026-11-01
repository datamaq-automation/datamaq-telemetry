"""tests/unit/test_realtime_por_planta.py — Issue datamaq#126: POST /api/v1/dispositivos/{id}/realtime respeta la planta.

La ruta activa `realtime_sync_mode` (hasta 600 s) en un medidor físico. Verificaba solo la organización
(`obtener_dispositivo_de_organizacion`), así que un usuario restringido por user_facility_access a la planta a1
podía ordenar una ráfaga sobre un medidor de la planta a2 de su misma organización. App completa con repositorios
SQLAlchemy reales sobre SQLite en memoria, la política real de acceso a plantas y la dependencia real
`verificar_propiedad_dispositivo`; el listener MQTT es un espía.
"""

from collections.abc import Callable, Iterator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.application.use_cases.gestionar_acceso_plantas import GestionarAccesoPlantasUseCase
from src.domain.auth.entities import AccesoPlantaUsuario
from src.domain.telemetria.entities import Planta
from src.infrastructure.fastapi.auth_dependencies import get_acceso_plantas_use_case
from src.infrastructure.fastapi.dependencies import get_usuario_actual
from src.infrastructure.fastapi.server import create_app
from src.infrastructure.sqlalchemy.database import get_db_session
from src.infrastructure.sqlalchemy.models import Base, DeviceModel, FacilityModel, OrganizationModel

PLANTA_ORG = {"planta-a1": "org-a", "planta-a2": "org-a", "planta-b": "org-b"}
UID = {"dev-a1": "AABBCCDDEE01", "dev-a2": "AABBCCDDEE02", "dev-b": "AABBCCDDEE03"}
PLANTA_DE = {"dev-a1": "planta-a1", "dev-a2": "planta-a2", "dev-b": "planta-b"}
RUTA_MQTT = "src.infrastructure.fastapi.routes.dispositivos_router.get_mqtt_listener"


@pytest.fixture()
def db() -> Iterator[Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    for org in ("org-a", "org-b"):
        session.add(OrganizationModel(id=org))
    for planta, org in PLANTA_ORG.items():
        session.add(FacilityModel(id=planta, organization_id=org, name=planta))
    for dev, planta in PLANTA_DE.items():
        session.add(DeviceModel(id=dev, facility_id=planta, device_uid=UID[dev]))
    session.commit()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def cliente(db: Session, monkeypatch) -> Callable[..., tuple[TestClient, MagicMock]]:
    """Fábrica de (cliente, listener espía) por claims y por plantas asignadas en user_facility_access."""
    monkeypatch.setattr(
        "src.infrastructure.fastapi.device_ownership.get_settings", lambda: MagicMock(AUTH_REQUIRED=True)
    )
    monkeypatch.setattr(
        "src.infrastructure.fastapi.device_ownership._resolver_organizacion_planta",
        lambda planta_id: PLANTA_ORG.get(planta_id or ""),
    )
    plantas = [Planta(id=p, organizacion_id=o, nombre=p) for p, o in PLANTA_ORG.items()]
    repo_org = MagicMock()
    repo_org.listar_plantas.side_effect = lambda org=None: [
        p for p in plantas if org is None or p.organizacion_id == org
    ]

    def _crear(claims: dict, plantas_asignadas: list[str]) -> tuple[TestClient, MagicMock]:
        accesos = [AccesoPlantaUsuario(usuario_id="u1", planta_id=p, puede_cambiar=False) for p in plantas_asignadas]
        acceso = GestionarAccesoPlantasUseCase(MagicMock(listar_por_usuario=lambda uid: accesos), repo_org)
        listener = MagicMock()
        listener.activar_tiempo_real_dispositivo.return_value = True
        app = create_app()
        app.dependency_overrides[get_db_session] = lambda: db
        app.dependency_overrides[get_usuario_actual] = lambda: claims
        app.dependency_overrides[get_acceso_plantas_use_case] = lambda: acceso
        return TestClient(app), listener

    return _crear


OPERADOR_A = {"sub": "u1", "rol": "operador", "org": "org-a"}


def _pedir_rafaga(client: TestClient, listener: MagicMock, dispositivo: str, segundos: int = 600):
    with patch(RUTA_MQTT, return_value=listener):
        return client.post(f"/api/v1/dispositivos/{dispositivo}/realtime?segundos={segundos}")


def test_restringido_a_una_planta_no_puede_pedir_rafaga_en_otra_planta_de_su_organizacion(cliente):
    client, listener = cliente(OPERADOR_A, ["planta-a1"])

    response = _pedir_rafaga(client, listener, "dev-a2")

    assert response.status_code == 404
    listener.activar_tiempo_real_dispositivo.assert_not_called()


def test_restringido_a_una_planta_si_puede_pedir_rafaga_en_su_planta(cliente):
    client, listener = cliente(OPERADOR_A, ["planta-a1"])

    response = _pedir_rafaga(client, listener, "dev-a1", segundos=300)

    assert response.status_code == 200
    assert response.json()["tiempo_real_activado"] is True
    listener.activar_tiempo_real_dispositivo.assert_called_once_with(UID["dev-a1"], segundos=300)


def test_usuario_sin_restriccion_de_planta_pide_rafaga_en_cualquier_planta_de_su_organizacion(cliente):
    client, listener = cliente(OPERADOR_A, [])

    assert _pedir_rafaga(client, listener, "dev-a2").status_code == 200
    listener.activar_tiempo_real_dispositivo.assert_called_once_with(UID["dev-a2"], segundos=600)


def test_superadmin_pide_rafaga_en_cualquier_planta(cliente):
    client, listener = cliente({"sub": "root", "rol": "superadmin"}, [])

    assert _pedir_rafaga(client, listener, "dev-a2").status_code == 200
    assert _pedir_rafaga(client, listener, "dev-b").status_code == 200
    assert listener.activar_tiempo_real_dispositivo.call_count == 2


def test_otra_organizacion_sigue_recibiendo_404(cliente):
    client, listener = cliente({"sub": "u2", "rol": "operador", "org": "org-b"}, [])

    response = _pedir_rafaga(client, listener, "dev-a1")

    assert response.status_code == 404
    listener.activar_tiempo_real_dispositivo.assert_not_called()


def test_solo_lectura_sigue_recibiendo_403_antes_que_la_comprobacion_de_planta(cliente):
    client, listener = cliente({"sub": "u3", "rol": "solo_lectura", "org": "org-a"}, ["planta-a1"])

    response = _pedir_rafaga(client, listener, "dev-a2")

    assert response.status_code == 403
    listener.activar_tiempo_real_dispositivo.assert_not_called()
