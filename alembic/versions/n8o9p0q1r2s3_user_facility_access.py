"""user_facility_access: asignación de plantas por usuario (R-02 del frontend)

Sin filas para un usuario se mantiene el comportamiento histórico (todas las
plantas de su organización, con permiso de cambio), así que la migración no
necesita backfill. `facility_id` no lleva FK porque las plantas viven en el YAML
declarativo (`data/organizaciones.yml`), no en `facilities`.

Revision ID: n8o9p0q1r2s3
Revises: m7n8o9p0q1r2
Create Date: 2026-09-13 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "n8o9p0q1r2s3"
down_revision: str | Sequence[str] | None = "m7n8o9p0q1r2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLA = "user_facility_access"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(TABLA):
        return
    op.create_table(
        TABLA,
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("facility_id", sa.String(36), primary_key=True),
        sa.Column("can_switch", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_user_facility_access_facility", TABLA, ["facility_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(TABLA):
        op.drop_table(TABLA)
