"""drop facility_zones y facility_device_layouts: duplicados muertos del YAML

Zonas y layout de planta viven en `data/organizaciones.yml` (modelo declarativo
ISA-95). Estas dos tablas quedaron de la etapa MySQL y ningún endpoint las leía:
`dependencies.py` siempre inyecta `YamlOrganizacionesRepository` para la
estructura de planta. Mismo caso que `unifilar_nodes` (k5l6m7n8o9p0).

Revision ID: o9p0q1r2s3t4
Revises: n8o9p0q1r2s3
Create Date: 2026-09-13 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "o9p0q1r2s3t4"
down_revision: str | Sequence[str] | None = "n8o9p0q1r2s3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    # layouts primero: tiene FK a facility_zones
    if inspector.has_table("facility_device_layouts"):
        op.drop_table("facility_device_layouts")
    if inspector.has_table("facility_zones"):
        op.drop_table("facility_zones")


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
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
