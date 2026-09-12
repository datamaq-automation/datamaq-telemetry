"""drop unused unifilar_nodes table

El diagrama unifilar (NodoUnifilar) se persiste en YamlOrganizacionesRepository
(dependencies.py); el backend SQL nunca estuvo enchufado vía DI y la tabla
quedó sin filas ni consumidores reales. FacilityUnifilarNodeModel se elimina
del ORM en el mismo cambio.

Revision ID: k5l6m7n8o9p0
Revises: j4k5l6m7n8o9
Create Date: 2026-09-12 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "k5l6m7n8o9p0"
down_revision: str | Sequence[str] | None = "j4k5l6m7n8o9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("unifilar_nodes"):
        op.drop_table("unifilar_nodes")


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("unifilar_nodes"):
        op.create_table(
            "unifilar_nodes",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("facility_id", sa.String(36), sa.ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False),
            sa.Column("parent_id", sa.String(36), nullable=True),
            sa.Column("name", sa.String(150), nullable=False),
            sa.Column("node_type", sa.String(50), nullable=False),
            sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id", ondelete="SET NULL"), nullable=True),
            sa.Column("nominal_voltage_v", sa.Numeric(8, 2), nullable=False),
            sa.Column("nominal_capacity_kva", sa.Numeric(10, 2), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("idx_unifilar_facility", "unifilar_nodes", ["facility_id"])
        op.create_index("idx_unifilar_parent", "unifilar_nodes", ["parent_id"])
