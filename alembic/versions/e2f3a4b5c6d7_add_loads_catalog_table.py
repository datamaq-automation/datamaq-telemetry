"""add loads catalog table (desagregacion de cargas / NILM)

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-09-04 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2f3a4b5c6d7"
down_revision: str | Sequence[str] | None = "d1e2f3a4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table("loads"):
        op.create_table(
            "loads",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("category", sa.String(30), nullable=False, server_default="OTROS"),
            sa.Column("electrical_nature", sa.String(20), nullable=False, server_default="MIXTA"),
            sa.Column("operation_pattern", sa.String(30), nullable=False, server_default="INDETERMINADO"),
            sa.Column("nameplate_power_w", sa.Numeric(10, 2), nullable=True),
            sa.Column("signature_power_w", sa.Numeric(10, 2), nullable=True),
            sa.Column("signature_dispersion_w", sa.Numeric(10, 2), nullable=True),
            sa.Column("signature_reactive_var", sa.Numeric(10, 2), nullable=True),
            sa.Column("signature_power_factor", sa.Numeric(4, 3), nullable=True),
            sa.Column("signature_on_seconds", sa.Numeric(10, 1), nullable=True),
            sa.Column("signature_on_mad_seconds", sa.Numeric(10, 1), nullable=True),
            sa.Column("signature_off_seconds", sa.Numeric(10, 1), nullable=True),
            sa.Column("signature_startup_peak_w", sa.Numeric(10, 2), nullable=True),
            sa.Column("signature_source", sa.String(20), nullable=True),
            sa.Column("signature_samples", sa.Integer(), nullable=True),
            sa.Column("signature_measured_at", sa.DateTime(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            # Un medidor agregado ve N cargas (a diferencia de `machines`, que es 1:1 con el
            # dispositivo): la unicidad es por nombre dentro del medidor, no por dispositivo.
            # Va dentro del CREATE TABLE y no como ALTER posterior porque SQLite —donde corre
            # `tests/unit/test_migraciones.py`— no soporta ALTER de constraints.
            sa.UniqueConstraint("device_id", "name", name="uq_loads_device_name"),
        )
        op.create_index("idx_loads_device", "loads", ["device_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("loads"):
        op.drop_table("loads")
