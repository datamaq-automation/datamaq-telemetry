"""feat(auth): crear tablas cambio_contrasena_validaciones y auditoria_cambio_contrasena

Revision ID: z0a1b2c3d4e5
Revises: y9z0a1b2c3d4
Create Date: 2026-10-05 23:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "z0a1b2c3d4e5"
down_revision: str | Sequence[str] | None = "y9z0a1b2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cambio_contrasena_validaciones",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.String(36), nullable=False),
        sa.Column("codigo", sa.String(4), nullable=False),
        sa.Column("ttl_expira", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumido_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_cambio_contrasena_validaciones_usuario_creado",
        "cambio_contrasena_validaciones",
        ["usuario_id", "creado_en"],
    )

    op.create_table(
        "auditoria_cambio_contrasena",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.String(36), nullable=False),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.Column("estado", sa.String(50), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_auditoria_cambio_contrasena_usuario_creado", "auditoria_cambio_contrasena", ["usuario_id", "creado_en"]
    )


def downgrade() -> None:
    op.drop_index("idx_auditoria_cambio_contrasena_usuario_creado", table_name="auditoria_cambio_contrasena")
    op.drop_table("auditoria_cambio_contrasena")
    op.drop_index("idx_cambio_contrasena_validaciones_usuario_creado", table_name="cambio_contrasena_validaciones")
    op.drop_table("cambio_contrasena_validaciones")
