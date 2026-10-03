"""add audit_asistente_consentimiento table for Groq consent tracking

Revision ID: x8y9z0a1b2c3
Revises: w7x8y9z0a1b2
Create Date: 2026-10-03 19:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "x8y9z0a1b2c3"
down_revision: str | Sequence[str] | None = "w7x8y9z0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table("audit_asistente_consentimiento"):
        op.create_table(
            "audit_asistente_consentimiento",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("usuario_id", sa.String(36), nullable=False),
            sa.Column(
                "organizacion_id",
                sa.String(36),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("consentimiento_otorgado", sa.Boolean(), nullable=False),
            sa.Column("fecha", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("ip_address", sa.String(45), nullable=True),
            sa.Column("user_agent", sa.Text(), nullable=True),
        )
        # Index para auditoría rápida: (usuario_id, fecha)
        op.create_index(
            "idx_audit_asistente_consentimiento_usuario_fecha",
            "audit_asistente_consentimiento",
            ["usuario_id", "fecha"],
        )
        # Index para listar por organización
        op.create_index(
            "idx_audit_asistente_consentimiento_org",
            "audit_asistente_consentimiento",
            ["organizacion_id"],
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("audit_asistente_consentimiento"):
        op.drop_table("audit_asistente_consentimiento")
