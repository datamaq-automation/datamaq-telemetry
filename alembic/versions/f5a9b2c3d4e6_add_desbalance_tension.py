"""add desbalance tension

Revision ID: f5a9b2c3d4e6
Revises: 2e6e9c693368
Create Date: 2026-08-22 10:35:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f5a9b2c3d4e6"
down_revision: str | Sequence[str] | None = "2e6e9c693368"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tiene_columna(inspector: sa.Inspector, tabla: str, columna: str) -> bool:
    if not inspector.has_table(tabla):
        return False
    return any(c["name"] == columna for c in inspector.get_columns(tabla))


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("telemetry_instantaneous"):
        if not _tiene_columna(inspector, "telemetry_instantaneous", "desbalance_tension_porcentaje"):
            op.add_column(
                "telemetry_instantaneous",
                sa.Column("desbalance_tension_porcentaje", sa.Numeric(5, 2), nullable=True),
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("telemetry_instantaneous"):
        if _tiene_columna(inspector, "telemetry_instantaneous", "desbalance_tension_porcentaje"):
            op.drop_column("telemetry_instantaneous", "desbalance_tension_porcentaje")
