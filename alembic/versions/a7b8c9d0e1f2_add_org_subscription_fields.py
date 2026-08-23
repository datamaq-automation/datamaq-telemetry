"""add pro_expires_at and free_tier_mode to organizations table

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-23 10:35:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: str | Sequence[str] | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tiene_columna(inspector: sa.Inspector, tabla: str, columna: str) -> bool:
    if not inspector.has_table(tabla):
        return False
    return any(c["name"] == columna for c in inspector.get_columns(tabla))


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("organizations"):
        if not _tiene_columna(inspector, "organizations", "pro_expires_at"):
            op.add_column(
                "organizations",
                sa.Column("pro_expires_at", sa.DateTime(), nullable=True),
            )
        if not _tiene_columna(inspector, "organizations", "free_tier_mode"):
            op.add_column(
                "organizations",
                sa.Column(
                    "free_tier_mode",
                    sa.String(30),
                    server_default="PRIVADO_BASICO",
                    nullable=False,
                ),
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("organizations"):
        if _tiene_columna(inspector, "organizations", "free_tier_mode"):
            op.drop_column("organizations", "free_tier_mode")
        if _tiene_columna(inspector, "organizations", "pro_expires_at"):
            op.drop_column("organizations", "pro_expires_at")
