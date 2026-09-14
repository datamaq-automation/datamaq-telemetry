"""tests/unit/test_verificador_notificaciones.py — gating de notificaciones por plan (Fase 2)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.domain.telemetria.entities import Organizacion, Planta
from src.domain.telemetria.ports import RepositorioOrganizacionesPort
from src.infrastructure.paho_mqtt.verificador_notificaciones import (
    construir_verificador_notificaciones,
)
from src.infrastructure.sqlalchemy.models import Base, DeviceModel, OrganizationModel


class FakeOrganizacionesRepo(RepositorioOrganizacionesPort):
    def __init__(self):
        self.organizaciones: dict[str, Organizacion] = {}
        self.plantas: dict[str, Planta] = {}

    def obtener_por_id(self, organizacion_id):
        return self.organizaciones.get(organizacion_id)

    def listar_organizaciones(self):
        return list(self.organizaciones.values())

    def guardar_organizacion(self, org):
        self.organizaciones[org.id] = org
        return org

    def obtener_planta_por_id(self, planta_id):
        return self.plantas.get(planta_id)

    def listar_plantas(self, organizacion_id=None):
        return list(self.plantas.values())

    def obtener_nodos_unifilar(self, planta_id):
        return []

    def obtener_zonas_planta(self, planta_id):
        return []

    def obtener_dispositivos_layout(self, planta_id):
        return []

    def obtener_instalacion_medidor(self, dispositivo_id):
        return None


def _session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _crear_dispositivo(session_factory, device_id: str, facility_id: str | None) -> None:
    mac = f"AA:BB:CC:DD:{abs(hash(device_id)) % 100:02d}:01"
    db = session_factory()
    db.add(DeviceModel(id=device_id, facility_id=facility_id, device_uid=mac))
    db.commit()
    db.close()


def test_dispositivo_sin_planta_no_restringe():
    sf = _session_factory()
    _crear_dispositivo(sf, "dev-suelto", facility_id=None)
    verificar = construir_verificador_notificaciones(sf, FakeOrganizacionesRepo())

    assert verificar("dev-suelto") is True


def test_dispositivo_inexistente_no_restringe():
    sf = _session_factory()
    verificar = construir_verificador_notificaciones(sf, FakeOrganizacionesRepo())

    assert verificar("no-existe") is True


def test_organizacion_pro_vigente_habilita_notificaciones():
    sf = _session_factory()
    _crear_dispositivo(sf, "dev-pro", facility_id="planta-1")
    repo_org = FakeOrganizacionesRepo()
    repo_org.plantas["planta-1"] = Planta(id="planta-1", organizacion_id="org-1", nombre="Planta 1")
    repo_org.organizaciones["org-1"] = Organizacion(id="org-1", nombre="Cliente PRO")

    db = sf()
    db.add(
        OrganizationModel(
            id="org-1", pro_expires_at=datetime.now(timezone.utc) + timedelta(days=10), free_tier_mode="PRIVADO_BASICO"
        )
    )
    db.commit()
    db.close()

    verificar = construir_verificador_notificaciones(sf, repo_org)
    assert verificar("dev-pro") is True


def test_organizacion_free_deshabilita_notificaciones():
    sf = _session_factory()
    _crear_dispositivo(sf, "dev-free", facility_id="planta-2")
    repo_org = FakeOrganizacionesRepo()
    repo_org.plantas["planta-2"] = Planta(id="planta-2", organizacion_id="org-2", nombre="Planta 2")
    repo_org.organizaciones["org-2"] = Organizacion(id="org-2", nombre="Cliente Free")
    # Sin fila en OrganizationModel: Suscripcion.por_defecto -> no PRO vigente.

    verificar = construir_verificador_notificaciones(sf, repo_org)
    assert verificar("dev-free") is False


def test_organizacion_con_pro_vencido_deshabilita_notificaciones():
    sf = _session_factory()
    _crear_dispositivo(sf, "dev-vencido", facility_id="planta-3")
    repo_org = FakeOrganizacionesRepo()
    repo_org.plantas["planta-3"] = Planta(id="planta-3", organizacion_id="org-3", nombre="Planta 3")
    repo_org.organizaciones["org-3"] = Organizacion(id="org-3", nombre="Cliente Vencido")

    db = sf()
    db.add(
        OrganizationModel(
            id="org-3", pro_expires_at=datetime.now(timezone.utc) - timedelta(days=1), free_tier_mode="PRIVADO_BASICO"
        )
    )
    db.commit()
    db.close()

    verificar = construir_verificador_notificaciones(sf, repo_org)
    assert verificar("dev-vencido") is False
