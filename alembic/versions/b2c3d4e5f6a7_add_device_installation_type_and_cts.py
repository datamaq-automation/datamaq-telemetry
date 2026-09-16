"""add installation_type and phases_with_ct to devices

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-22 12:28:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tiene_columna(inspector: sa.Inspector, tabla: str, columna: str) -> bool:
    if not inspector.has_table(tabla):
        return False
    return any(c["name"] == columna for c in inspector.get_columns(tabla))


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("devices"):
        if not _tiene_columna(inspector, "devices", "installation_type"):
            op.add_column(
                "devices",
                sa.Column("installation_type", sa.String(30), server_default="CONSUMO", nullable=False),
            )
        if not _tiene_columna(inspector, "devices", "phases_with_ct"):
            op.add_column(
                "devices",
                sa.Column("phases_with_ct", sa.String(20), server_default="R,S,T", nullable=False),
            )
        if not _tiene_columna(inspector, "devices", "ct_inverted_phases"):
            op.add_column(
                "devices",
                sa.Column("ct_inverted_phases", sa.String(10), nullable=True),
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("devices"):
        if _tiene_columna(inspector, "devices", "ct_inverted_phases"):
            op.drop_column("devices", "ct_inverted_phases")
        if _tiene_columna(inspector, "devices", "phases_with_ct"):
            op.drop_column("devices", "phases_with_ct")
        if _tiene_columna(inspector, "devices", "installation_type"):
            op.drop_column("devices", "installation_type")
