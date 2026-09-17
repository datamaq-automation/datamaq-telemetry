"""add device phase angle offsets

Revision ID: s3t4u5v6w7x8
Revises: r2s3t4u5v6w7
Create Date: 2026-09-17 09:41:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "s3t4u5v6w7x8"
down_revision: str | Sequence[str] | None = "r2s3t4u5v6w7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tiene_columna(inspector: sa.Inspector, tabla: str, columna: str) -> bool:
    if not inspector.has_table(tabla):
        return False
    return any(c["name"] == columna for c in inspector.get_columns(tabla))


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("devices"):
        if not _tiene_columna(inspector, "devices", "ct_phase_angle_offsets"):
            op.add_column(
                "devices",
                sa.Column("ct_phase_angle_offsets", sa.String(50), server_default="", nullable=False),
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("devices"):
        if _tiene_columna(inspector, "devices", "ct_phase_angle_offsets"):
            op.drop_column("devices", "ct_phase_angle_offsets")
