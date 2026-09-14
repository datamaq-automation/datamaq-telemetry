"""tests/unit/test_gestionar_suscripciones.py — ciclo de vida comercial de una organización."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.application.use_cases.gestionar_suscripciones import GestionarSuscripcionesUseCase
from src.domain.telemetria.exceptions import PlanNoEncontradoError
from src.domain.telemetria.value_objects import ModoFreeTier
from src.infrastructure.sqlalchemy.models import Base, PlanModel
from src.infrastructure.sqlalchemy.repositories.planes_repository import MySQLPlanesRepository
from src.infrastructure.sqlalchemy.repositories.suscripciones_repository import MySQLSuscripcionesRepository


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _crear_plan(db, **overrides) -> str:
    defaults = dict(
        id="plan-pro",
        name="PRO",
        description="Plan PRO",
        monthly_price_ars=5000,
        visibility="PUBLICO",
        retention_days=365,
        granularity_minutes=1,
        max_devices=10,
        notification_channels=["email"],
    )
    defaults.update(overrides)
    db.add(PlanModel(**defaults))
    db.commit()
    return defaults["id"]


def _use_case(db) -> GestionarSuscripcionesUseCase:
    return GestionarSuscripcionesUseCase(MySQLSuscripcionesRepository(db), MySQLPlanesRepository(db))


def test_activar_o_extender_con_plan_inexistente_falla():
    db = _session()
    uc = _use_case(db)
    with pytest.raises(PlanNoEncontradoError):
        uc.activar_o_extender("org-1", "plan-fantasma", datetime.now(timezone.utc) + timedelta(days=30))


def test_activar_o_extender_crea_suscripcion_vigente():
    db = _session()
    plan_id = _crear_plan(db)
    uc = _use_case(db)
    hasta = datetime.now(timezone.utc) + timedelta(days=30)

    suscripcion = uc.activar_o_extender("org-1", plan_id, hasta)

    assert suscripcion.plan_id == plan_id
    assert suscripcion.pro_vence_en is not None
    assert suscripcion.pro_vence_en.date() == hasta.date()


def test_activar_o_extender_preserva_modo_free_previo():
    db = _session()
    plan_id = _crear_plan(db)
    repo_suscripciones = MySQLSuscripcionesRepository(db)
    uc = GestionarSuscripcionesUseCase(repo_suscripciones, MySQLPlanesRepository(db))
    hasta = datetime.now(timezone.utc) + timedelta(days=30)
    uc.activar_o_extender("org-1", plan_id, hasta)

    # Simula que la organización tenía vitrina anónima antes de pagar.
    actual = repo_suscripciones.obtener_por_organizacion("org-1")
    actual.modo_free = ModoFreeTier.VITRINA_ANONIMA
    repo_suscripciones.guardar(actual)

    extendida = uc.activar_o_extender("org-1", plan_id, hasta + timedelta(days=30))
    assert extendida.modo_free is ModoFreeTier.VITRINA_ANONIMA


def test_cancelar_baja_inmediata_sin_esperar_vencimiento():
    db = _session()
    plan_id = _crear_plan(db)
    uc = _use_case(db)
    uc.activar_o_extender("org-1", plan_id, datetime.now(timezone.utc) + timedelta(days=30))

    cancelada = uc.cancelar("org-1")

    assert cancelada.pro_vence_en is None
    assert cancelada.modo_free is ModoFreeTier.PRIVADO_BASICO
    assert cancelada.plan_id == plan_id  # conserva el plan para poder reactivar sin re-elegirlo


def test_expirar_vencidas_baja_solo_las_que_ya_vencieron():
    db = _session()
    plan_id = _crear_plan(db)
    uc = _use_case(db)
    ahora = datetime.now(timezone.utc)
    uc.activar_o_extender("org-vencida", plan_id, ahora - timedelta(days=1))
    uc.activar_o_extender("org-vigente", plan_id, ahora + timedelta(days=10))

    afectadas = uc.expirar_vencidas(ahora)

    assert [s.organizacion_id for s in afectadas] == ["org-vencida"]
    repo = MySQLSuscripcionesRepository(db)
    assert repo.obtener_por_organizacion("org-vencida").modo_free is ModoFreeTier.PRIVADO_BASICO
    assert repo.obtener_por_organizacion("org-vigente").pro_vence_en is not None


def test_expirar_vencidas_es_idempotente_no_reprocesa_ya_expiradas():
    db = _session()
    plan_id = _crear_plan(db)
    uc = _use_case(db)
    ahora = datetime.now(timezone.utc)
    uc.activar_o_extender("org-vencida", plan_id, ahora - timedelta(days=1))

    primera_pasada = uc.expirar_vencidas(ahora)
    segunda_pasada = uc.expirar_vencidas(ahora)

    assert len(primera_pasada) == 1
    assert len(segunda_pasada) == 0
