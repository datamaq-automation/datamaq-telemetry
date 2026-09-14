"""tests/unit/test_webhook_events_repository.py."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.infrastructure.sqlalchemy.models import Base
from src.infrastructure.sqlalchemy.repositories.webhook_events_repository import (
    MySQLRegistroEventosWebhook,
)


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_evento_no_registrado_no_esta_procesado():
    repo = MySQLRegistroEventosWebhook(_session())
    assert repo.ya_procesado("mercadopago", "evt-1") is False


def test_marcar_procesado_lo_deja_como_ya_procesado():
    db = _session()
    repo = MySQLRegistroEventosWebhook(db)
    repo.marcar_procesado("mercadopago", "evt-1")
    assert repo.ya_procesado("mercadopago", "evt-1") is True


def test_mismo_event_id_en_proveedores_distintos_no_colisiona():
    db = _session()
    repo = MySQLRegistroEventosWebhook(db)
    repo.marcar_procesado("mercadopago", "evt-1")
    assert repo.ya_procesado("otro-proveedor", "evt-1") is False


def test_marcar_procesado_dos_veces_no_rompe_idempotencia():
    db = _session()
    repo = MySQLRegistroEventosWebhook(db)
    repo.marcar_procesado("mercadopago", "evt-1")
    repo.marcar_procesado("mercadopago", "evt-1")  # reenvío del webhook, no debe explotar
    assert repo.ya_procesado("mercadopago", "evt-1") is True
