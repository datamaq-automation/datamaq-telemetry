"""src/infrastructure/sqlalchemy/repositories/webhook_events_repository.py."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.domain.billing.ports import RegistroEventosWebhookPort
from src.infrastructure.sqlalchemy.models import WebhookEventModel


class MySQLRegistroEventosWebhook(RegistroEventosWebhookPort):
    def __init__(self, db: Session):
        self.db = db

    def ya_procesado(self, proveedor: str, event_id: str) -> bool:
        return (
            self.db.query(WebhookEventModel)
            .filter(WebhookEventModel.provider == proveedor, WebhookEventModel.event_id == event_id)
            .first()
            is not None
        )

    def marcar_procesado(self, proveedor: str, event_id: str) -> None:
        self.db.add(WebhookEventModel(provider=proveedor, event_id=event_id))
        try:
            self.db.commit()
        except IntegrityError:
            # Dos requests concurrentes del mismo evento: la unique constraint gana la carrera,
            # el perdedor solo necesita saber que ya quedó registrado por el otro.
            self.db.rollback()
