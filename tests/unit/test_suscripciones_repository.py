"""tests/unit/test_suscripciones_repository.py — `organizations` como suscripción (E2)."""

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.domain.telemetria.entities import Suscripcion
from src.domain.telemetria.value_objects import ModoFreeTier
from src.infrastructure.sqlalchemy.models import Base, OrganizationModel
from src.infrastructure.sqlalchemy.repositories.suscripciones_repository import MySQLSuscripcionesRepository


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_sin_fila_devuelve_none_y_el_dominio_cae_al_default():
    repo = MySQLSuscripcionesRepository(_session())
    assert repo.obtener_por_organizacion("org-x") is None
    default = Suscripcion.por_defecto("org-x")
    assert default.modo_free is ModoFreeTier.PRIVADO_BASICO
    assert default.plan_id is None and default.pro_vence_en is None


def test_guardar_crea_y_actualiza():
    repo = MySQLSuscripcionesRepository(_session())
    vence = datetime(2026, 12, 31, tzinfo=timezone.utc)
    creada = repo.guardar(
        Suscripcion(organizacion_id="org-1", plan_id=None, pro_vence_en=vence, modo_free=ModoFreeTier.PRIVADO_BASICO)
    )
    assert creada.modo_free is ModoFreeTier.PRIVADO_BASICO
    assert creada.pro_vence_en is not None and creada.pro_vence_en.date() == vence.date()

    repo.guardar(Suscripcion(organizacion_id="org-1", modo_free=ModoFreeTier.PRIVADO_BASICO))
    leida = repo.obtener_por_organizacion("org-1")
    assert leida is not None and leida.modo_free is ModoFreeTier.PRIVADO_BASICO
    assert leida.pro_vence_en is None


def test_free_tier_desconocido_en_base_cae_a_privado_basico():
    db = _session()
    db.add(OrganizationModel(id="org-raro", free_tier_mode="LO_QUE_SEA"))
    db.commit()
    leida = MySQLSuscripcionesRepository(db).obtener_por_organizacion("org-raro")
    assert leida is not None and leida.modo_free is ModoFreeTier.PRIVADO_BASICO
