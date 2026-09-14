"""tests/unit/test_procesar_webhook_mercadopago.py."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.application.use_cases.billing.procesar_webhook_mercadopago import (
    ProcesarWebhookMercadoPagoUseCase,
)
from src.application.use_cases.gestionar_suscripciones import GestionarSuscripcionesUseCase
from src.domain.billing.entities import PreapprovalCreado, PreapprovalInfo
from src.domain.billing.ports import ProveedorPagosPort
from src.infrastructure.sqlalchemy.models import Base, PlanModel
from src.infrastructure.sqlalchemy.repositories.planes_repository import MySQLPlanesRepository
from src.infrastructure.sqlalchemy.repositories.suscripciones_repository import MySQLSuscripcionesRepository


class FakeProveedorPagos(ProveedorPagosPort):
    def __init__(self, info: PreapprovalInfo):
        self.info = info

    def crear_preapproval(self, *args, **kwargs):
        return PreapprovalCreado(id="x", init_point="https://x")

    def obtener_preapproval(self, preapproval_id):
        return self.info


class FakeRegistroEventos:
    def __init__(self):
        self.procesados: set[tuple[str, str]] = set()

    def ya_procesado(self, proveedor, event_id):
        return (proveedor, event_id) in self.procesados

    def marcar_procesado(self, proveedor, event_id):
        self.procesados.add((proveedor, event_id))


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _crear_plan(db, plan_id="plan-pro") -> str:
    db.add(
        PlanModel(
            id=plan_id,
            name="PRO",
            description="Plan PRO",
            monthly_price_ars=5000,
            visibility="PUBLICO",
            retention_days=365,
            granularity_minutes=1,
            max_devices=10,
            notification_channels=["email"],
        )
    )
    db.commit()
    return plan_id


def _gestionar_suscripciones(db) -> GestionarSuscripcionesUseCase:
    return GestionarSuscripcionesUseCase(MySQLSuscripcionesRepository(db), MySQLPlanesRepository(db))


def test_evento_duplicado_no_se_reprocesa():
    db = _session()
    plan_id = _crear_plan(db)
    registro = FakeRegistroEventos()
    registro.marcar_procesado("mercadopago", "evt-1")
    proveedor = FakeProveedorPagos(
        PreapprovalInfo(
            id="preap-1", status="authorized", external_reference=f"org-1:{plan_id}", next_payment_date=None
        )
    )
    uc = ProcesarWebhookMercadoPagoUseCase(proveedor, registro, _gestionar_suscripciones(db))

    resultado = uc.ejecutar("evt-1", "preap-1")

    assert resultado.procesado is False
    assert resultado.accion == "ignorado_duplicado"


def test_authorized_activa_la_suscripcion_hasta_next_payment_date():
    db = _session()
    plan_id = _crear_plan(db)
    hasta = datetime.now(timezone.utc) + timedelta(days=30)
    proveedor = FakeProveedorPagos(
        PreapprovalInfo(
            id="preap-1", status="authorized", external_reference=f"org-1:{plan_id}", next_payment_date=hasta
        )
    )
    registro = FakeRegistroEventos()
    uc = ProcesarWebhookMercadoPagoUseCase(proveedor, registro, _gestionar_suscripciones(db))

    resultado = uc.ejecutar("evt-1", "preap-1")

    assert resultado.accion == "activado"
    sus = MySQLSuscripcionesRepository(db).obtener_por_organizacion("org-1")
    assert sus.plan_id == plan_id
    assert sus.pro_vence_en.date() == hasta.date()
    assert registro.ya_procesado("mercadopago", "evt-1") is True


def test_cancelled_da_de_baja_inmediata():
    db = _session()
    plan_id = _crear_plan(db)
    gestionar = _gestionar_suscripciones(db)
    gestionar.activar_o_extender("org-1", plan_id, datetime.now(timezone.utc) + timedelta(days=30))

    proveedor = FakeProveedorPagos(
        PreapprovalInfo(id="preap-1", status="cancelled", external_reference=f"org-1:{plan_id}", next_payment_date=None)
    )
    uc = ProcesarWebhookMercadoPagoUseCase(proveedor, FakeRegistroEventos(), gestionar)

    resultado = uc.ejecutar("evt-2", "preap-1")

    assert resultado.accion == "cancelado"
    sus = MySQLSuscripcionesRepository(db).obtener_por_organizacion("org-1")
    assert sus.pro_vence_en is None


def test_paused_tambien_da_de_baja():
    db = _session()
    plan_id = _crear_plan(db)
    gestionar = _gestionar_suscripciones(db)
    gestionar.activar_o_extender("org-1", plan_id, datetime.now(timezone.utc) + timedelta(days=30))

    proveedor = FakeProveedorPagos(
        PreapprovalInfo(id="preap-1", status="paused", external_reference=f"org-1:{plan_id}", next_payment_date=None)
    )
    uc = ProcesarWebhookMercadoPagoUseCase(proveedor, FakeRegistroEventos(), gestionar)

    resultado = uc.ejecutar("evt-3", "preap-1")

    assert resultado.accion == "cancelado"


def test_status_pendiente_no_cambia_nada_pero_marca_procesado():
    db = _session()
    plan_id = _crear_plan(db)
    proveedor = FakeProveedorPagos(
        PreapprovalInfo(id="preap-1", status="pending", external_reference=f"org-1:{plan_id}", next_payment_date=None)
    )
    registro = FakeRegistroEventos()
    uc = ProcesarWebhookMercadoPagoUseCase(proveedor, registro, _gestionar_suscripciones(db))

    resultado = uc.ejecutar("evt-4", "preap-1")

    assert resultado.accion == "sin_cambios"
    assert registro.ya_procesado("mercadopago", "evt-4") is True


def test_external_reference_invalida_no_rompe_y_marca_procesado():
    db = _session()
    proveedor = FakeProveedorPagos(
        PreapprovalInfo(id="preap-1", status="authorized", external_reference=None, next_payment_date=None)
    )
    registro = FakeRegistroEventos()
    uc = ProcesarWebhookMercadoPagoUseCase(proveedor, registro, _gestionar_suscripciones(db))

    resultado = uc.ejecutar("evt-5", "preap-1")

    assert resultado.accion == "referencia_invalida"
    assert registro.ya_procesado("mercadopago", "evt-5") is True
