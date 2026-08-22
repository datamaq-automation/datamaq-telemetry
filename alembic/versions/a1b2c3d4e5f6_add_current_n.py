"""add current_n to telemetry_instantaneous

Revision ID: a1b2c3d4e5f6
Revises: f5a9b2c3d4e6
Create Date: 2026-08-22 12:05:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "f5a9b2c3d4e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tiene_columna(inspector: sa.Inspector, tabla: str, columna: str) -> bool:
    if not inspector.has_table(tabla):
        return False
    return any(c["name"] == columna for c in inspector.get_columns(tabla))


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not _tiene_columna(inspector, "telemetry_instantaneous", "current_n"):
        op.add_column(
            "telemetry_instantaneous",
            sa.Column("current_n", sa.Numeric(6, 2), nullable=True),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if _tiene_columna(inspector, "telemetry_instantaneous", "current_n"):
        op.drop_column("telemetry_instantaneous", "current_n")
