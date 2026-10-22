"""feat(auditoria): crear tabla auditoria_cambios_ti

Revision ID: y9z0a1b2c3d4
Revises: x8y9z0a1b2c3
Create Date: 2026-10-05 22:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "y9z0a1b2c3d4"
down_revision: str | Sequence[str] | None = "x8y9z0a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auditoria_cambios_ti",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("device_id", sa.String(36), nullable=False),
        sa.Column("tipo_cambio", sa.String(100), nullable=False),
        sa.Column("valor_anterior", sa.Text(), nullable=True),
        sa.Column("valor_nuevo", sa.Text(), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("commit_git", sa.String(40), nullable=True),
        sa.Column("usuario", sa.String(100), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_dispositivo_timestamp", "auditoria_cambios_ti", ["device_id", "timestamp"])
    op.create_index("idx_tipo_cambio", "auditoria_cambios_ti", ["tipo_cambio"])


def downgrade() -> None:
    op.drop_index("idx_tipo_cambio", table_name="auditoria_cambios_ti")
    op.drop_index("idx_dispositivo_timestamp", table_name="auditoria_cambios_ti")
    op.drop_table("auditoria_cambios_ti")
