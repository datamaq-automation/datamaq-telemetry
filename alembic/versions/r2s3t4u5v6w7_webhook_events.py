"""webhook_events: idempotencia de webhooks de proveedores de pago (Fase 4 billing)

Un mismo evento reenviado por Mercado Pago (o cualquier otro proveedor a futuro) no
debe disparar dos veces la misma activación/baja de suscripción.

Revision ID: r2s3t4u5v6w7
Revises: q1r2s3t4u5v6
Create Date: 2026-09-14 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "r2s3t4u5v6w7"
down_revision: str | Sequence[str] | None = "q1r2s3t4u5v6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("event_id", sa.String(100), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "event_id", name="uq_webhook_events_provider_event"),
    )


def downgrade() -> None:
    op.drop_table("webhook_events")
