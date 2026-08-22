"""add tension_neutro_estimada to telemetry_instantaneous

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-22 19:57:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tiene_columna(inspector: sa.Inspector, tabla: str, columna: str) -> bool:
    if not inspector.has_table(tabla):
        return False
    return any(c["name"] == columna for c in inspector.get_columns(tabla))


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("telemetry_instantaneous"):
        if not _tiene_columna(inspector, "telemetry_instantaneous", "tension_neutro_estimada"):
            op.add_column(
                "telemetry_instantaneous",
                sa.Column("tension_neutro_estimada", sa.Numeric(6, 2), nullable=True),
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("telemetry_instantaneous"):
        if _tiene_columna(inspector, "telemetry_instantaneous", "tension_neutro_estimada"):
            op.drop_column("telemetry_instantaneous", "tension_neutro_estimada")
