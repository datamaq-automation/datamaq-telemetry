"""add unifilar_nodes, facility_zones, facility_device_layouts tables and layout_svg_url

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-08-23 10:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8c9d0e1f2a3"
down_revision: str | Sequence[str] | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tiene_columna(inspector: sa.Inspector, tabla: str, columna: str) -> bool:
    if not inspector.has_table(tabla):
        return False
    return any(c["name"] == columna for c in inspector.get_columns(tabla))


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    # 1. Agregar layout_svg_url a facilities
    if inspector.has_table("facilities"):
        if not _tiene_columna(inspector, "facilities", "layout_svg_url"):
            op.add_column("facilities", sa.Column("layout_svg_url", sa.String(500), nullable=True))

    # 2. Crear tabla unifilar_nodes
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

    # 3. Crear tabla facility_zones
    if not inspector.has_table("facility_zones"):
        op.create_table(
            "facility_zones",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("facility_id", sa.String(36), sa.ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(150), nullable=False),
            sa.Column("x_pct", sa.Numeric(6, 2), nullable=False),
            sa.Column("y_pct", sa.Numeric(6, 2), nullable=False),
            sa.Column("width_pct", sa.Numeric(6, 2), nullable=False),
            sa.Column("height_pct", sa.Numeric(6, 2), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("idx_zone_facility", "facility_zones", ["facility_id"])

    # 4. Crear tabla facility_device_layouts
    if not inspector.has_table("facility_device_layouts"):
        op.create_table(
            "facility_device_layouts",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("facility_id", sa.String(36), sa.ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False),
            sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
            sa.Column("zone_id", sa.String(36), sa.ForeignKey("facility_zones.id", ondelete="SET NULL"), nullable=True),
            sa.Column("pos_x_pct", sa.Numeric(6, 2), nullable=False),
            sa.Column("pos_y_pct", sa.Numeric(6, 2), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("idx_layout_facility", "facility_device_layouts", ["facility_id"])
        op.create_index("idx_layout_device", "facility_device_layouts", ["device_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("facility_device_layouts"):
        op.drop_table("facility_device_layouts")
    if inspector.has_table("facility_zones"):
        op.drop_table("facility_zones")
    if inspector.has_table("unifilar_nodes"):
        op.drop_table("unifilar_nodes")
    if inspector.has_table("facilities") and _tiene_columna(inspector, "facilities", "layout_svg_url"):
        op.drop_column("facilities", "layout_svg_url")
