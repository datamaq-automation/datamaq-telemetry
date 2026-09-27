"""add es_cooperativa to organizations table

Revision ID: v6w7x8y9z0a1
Revises: u5v6w7x8y9z0
Create Date: 2026-09-27 17:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v6w7x8y9z0a1"
down_revision: str | Sequence[str] | None = "u5v6w7x8y9z0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tiene_columna(inspector: sa.Inspector, tabla: str, columna: str) -> bool:
    if not inspector.has_table(tabla):
        return False
    return any(c["name"] == columna for c in inspector.get_columns(tabla))


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("organizations"):
        if not _tiene_columna(inspector, "organizations", "es_cooperativa"):
            op.add_column(
                "organizations",
                sa.Column("es_cooperativa", sa.Boolean(), server_default="0", nullable=False),
            )
            # Marcar cooperativas conocidas (por ID)
            # Cooperativa de Trabajo Unión Papelera Platense Ltda: edebb9a0-85e5-4bde-a370-e64bd9b9608c
            # Cooperativa de Trabajo Los Constituyentes Ltda.: 20857cb6-eff2-4bd4-8cb9-36e4c63bcee3
            op.execute(
                "UPDATE organizations SET es_cooperativa = 1 WHERE id IN "
                "('edebb9a0-85e5-4bde-a370-e64bd9b9608c', '20857cb6-eff2-4bd4-8cb9-36e4c63bcee3')"
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("organizations"):
        if _tiene_columna(inspector, "organizations", "es_cooperativa"):
            op.drop_column("organizations", "es_cooperativa")
