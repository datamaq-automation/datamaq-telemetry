"""add voltage_linea_V to telemetry_instantaneous

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-22 16:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tiene_columna(inspector: sa.Inspector, tabla: str, columna: str) -> bool:
    if not inspector.has_table(tabla):
        return False
    return any(c["name"] == columna for c in inspector.get_columns(tabla))


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("telemetry_instantaneous"):
        if not _tiene_columna(inspector, "telemetry_instantaneous", "voltage_linea_V"):
            op.add_column(
                "telemetry_instantaneous",
                sa.Column("voltage_linea_V", sa.Numeric(6, 2), nullable=True),
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("telemetry_instantaneous"):
        if _tiene_columna(inspector, "telemetry_instantaneous", "voltage_linea_V"):
            op.drop_column("telemetry_instantaneous", "voltage_linea_V")
