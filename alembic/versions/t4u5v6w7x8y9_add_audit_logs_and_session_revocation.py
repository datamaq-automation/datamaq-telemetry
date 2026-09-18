"""add audit logs and session revocation

Revision ID: t4u5v6w7x8y9
Revises: s3t4u5v6w7x8
Create Date: 2026-09-18 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "t4u5v6w7x8y9"
down_revision: str | Sequence[str] | None = "s3t4u5v6w7x8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tiene_columna(inspector: sa.Inspector, tabla: str, columna: str) -> bool:
    if not inspector.has_table(tabla):
        return False
    return any(c["name"] == columna for c in inspector.get_columns(tabla))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. Tabla audit_logs (append-only)
    if not inspector.has_table("audit_logs"):
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("registrado_en", sa.DateTime(timezone=True), nullable=False),
            sa.Column("actor_usuario_id", sa.String(36), nullable=True),
            sa.Column("actor_email", sa.String(255), nullable=True),
            sa.Column("actor_ip", sa.String(45), nullable=True),
            sa.Column("actor_user_agent", sa.String(255), nullable=True),
            sa.Column("categoria", sa.String(50), nullable=False),
            sa.Column("accion", sa.String(100), nullable=False),
            sa.Column("resultado", sa.String(20), nullable=False),
            sa.Column("recurso_tipo", sa.String(50), nullable=True),
            sa.Column("recurso_id", sa.String(100), nullable=True),
            sa.Column("metadatos", sa.JSON(), nullable=True),
        )
        op.create_index("idx_audit_actor_fecha", "audit_logs", ["actor_usuario_id", "registrado_en"])
        op.create_index("idx_audit_recurso", "audit_logs", ["recurso_tipo", "recurso_id"])
        op.create_index("ix_audit_logs_actor_usuario_id", "audit_logs", ["actor_usuario_id"])
        op.create_index("ix_audit_logs_categoria", "audit_logs", ["categoria"])
        op.create_index("ix_audit_logs_accion", "audit_logs", ["accion"])
        op.create_index("ix_audit_logs_recurso_id", "audit_logs", ["recurso_id"])

    # 2. Columna sesiones_revocadas_antes_de en users
    if inspector.has_table("users"):
        if not _tiene_columna(inspector, "users", "sesiones_revocadas_antes_de"):
            op.add_column(
                "users",
                sa.Column("sesiones_revocadas_antes_de", sa.DateTime(timezone=True), nullable=True),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("users"):
        if _tiene_columna(inspector, "users", "sesiones_revocadas_antes_de"):
            op.drop_column("users", "sesiones_revocadas_antes_de")

    if inspector.has_table("audit_logs"):
        op.drop_index("ix_audit_logs_recurso_id", table_name="audit_logs")
        op.drop_index("ix_audit_logs_accion", table_name="audit_logs")
        op.drop_index("ix_audit_logs_categoria", table_name="audit_logs")
        op.drop_index("ix_audit_logs_actor_usuario_id", table_name="audit_logs")
        op.drop_index("idx_audit_recurso", table_name="audit_logs")
        op.drop_index("idx_audit_actor_fecha", table_name="audit_logs")
        op.drop_table("audit_logs")
