"""alertas_ultima_deteccion_y_ocurrencias
Revision ID: c4e8a1d2f6b9
Revises: 7603c19a617f
Create Date: 2026-10-11 22:30:00.000000

Una alerta abierta se actualiza en cada nueva detección en vez de abrir otra (#19): guarda la última detección y
cuántas veces se detectó. Las filas existentes quedan con ocurrencias=1 y sin última detección; las duplicadas
abiertas las consolida scripts/consolidar_alertas_duplicadas.py (lo corre el dueño).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e8a1d2f6b9"
down_revision: str | Sequence[str] | None = "7603c19a617f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("device_alerts", sa.Column("last_detected_at", sa.DateTime(), nullable=True))
    op.add_column("device_alerts", sa.Column("occurrences", sa.Integer(), server_default="1", nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("device_alerts", "occurrences")
    op.drop_column("device_alerts", "last_detected_at")
