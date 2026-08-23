"""add engineering fields to device_alerts

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-22 21:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tiene_columna(inspector: sa.Inspector, tabla: str, columna: str) -> bool:
    if not inspector.has_table(tabla):
        return False
    return any(c["name"] == columna for c in inspector.get_columns(tabla))


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("device_alerts"):
        if not _tiene_columna(inspector, "device_alerts", "phase"):
            op.add_column("device_alerts", sa.Column("phase", sa.String(10), nullable=True))
        if not _tiene_columna(inspector, "device_alerts", "measured_value"):
            op.add_column("device_alerts", sa.Column("measured_value", sa.Numeric(10, 2), nullable=True))
        if not _tiene_columna(inspector, "device_alerts", "threshold_value"):
            op.add_column("device_alerts", sa.Column("threshold_value", sa.Numeric(10, 2), nullable=True))
        if not _tiene_columna(inspector, "device_alerts", "unit"):
            op.add_column("device_alerts", sa.Column("unit", sa.String(20), nullable=True))
        if not _tiene_columna(inspector, "device_alerts", "category"):
            op.add_column("device_alerts", sa.Column("category", sa.String(50), nullable=True))
        if not _tiene_columna(inspector, "device_alerts", "notes"):
            op.add_column("device_alerts", sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("device_alerts"):
        for col in ("notes", "category", "unit", "threshold_value", "measured_value", "phase"):
            if _tiene_columna(inspector, "device_alerts", col):
                op.drop_column("device_alerts", col)
