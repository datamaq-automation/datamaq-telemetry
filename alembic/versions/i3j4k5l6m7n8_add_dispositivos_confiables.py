"""add dispositivos_confiables

Revision ID: i3j4k5l6m7n8
Revises: h2i3j4k5l6m7
Create Date: 2026-09-11 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "i3j4k5l6m7n8"
down_revision: str | Sequence[str] | None = "h2i3j4k5l6m7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table("dispositivos_confiables"):
        op.create_table(
            "dispositivos_confiables",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("usuario_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False),
            sa.Column("nombre_dispositivo", sa.String(150), nullable=True),
            sa.Column("user_agent", sa.String(255), nullable=False, server_default=""),
            sa.Column("ip_origen", sa.String(45), nullable=False, server_default=""),
            sa.Column("creado_en", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("ultimo_acceso_en", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("expira_en", sa.DateTime(), nullable=False),
            sa.Column("revocado", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.create_index("idx_dispositivos_confiables_usuario", "dispositivos_confiables", ["usuario_id"])
        op.create_index("idx_dispositivos_confiables_hash", "dispositivos_confiables", ["token_hash"], unique=True)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("dispositivos_confiables"):
        op.drop_table("dispositivos_confiables")
