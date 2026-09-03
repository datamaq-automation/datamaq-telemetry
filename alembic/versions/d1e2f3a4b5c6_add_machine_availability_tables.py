"""add machines, machine_availability_events, scheduled_stops tables

Revision ID: d1e2f3a4b5c6
Revises: 1f2e3d4c5b6a
Create Date: 2026-09-03 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: str | Sequence[str] | None = "1f2e3d4c5b6a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table("machines"):
        op.create_table(
            "machines",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "device_id", sa.String(36), sa.ForeignKey("devices.id", ondelete="CASCADE"), unique=True, nullable=False
            ),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("on_threshold_w", sa.Numeric(10, 2), nullable=True),
            sa.Column("persistence_readings", sa.Integer(), nullable=False, server_default="2"),
            sa.Column("persistence_seconds", sa.Numeric(8, 2), nullable=False, server_default="60.0"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )

    if not inspector.has_table("machine_availability_events"):
        op.create_table(
            "machine_availability_events",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("machine_id", sa.String(36), sa.ForeignKey("machines.id", ondelete="CASCADE"), nullable=False),
            sa.Column("state", sa.String(10), nullable=False),
            sa.Column("stop_type", sa.String(20), nullable=True),
            sa.Column("start_at", sa.DateTime(), nullable=False),
            sa.Column("end_at", sa.DateTime(), nullable=True),
            sa.Column("avg_power_w", sa.Numeric(10, 2), nullable=True),
            sa.Column("origin", sa.String(20), nullable=False, server_default="REGLA"),
            sa.Column("corrected_by_user_id", sa.String(36), nullable=True),
            sa.Column("corrected_at", sa.DateTime(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
        )
        op.create_index(
            "idx_machine_availability_machine_open", "machine_availability_events", ["machine_id", "end_at"]
        )

    if not inspector.has_table("scheduled_stops"):
        op.create_table(
            "scheduled_stops",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("machine_id", sa.String(36), sa.ForeignKey("machines.id", ondelete="CASCADE"), nullable=False),
            sa.Column("start_at", sa.DateTime(), nullable=False),
            sa.Column("end_at", sa.DateTime(), nullable=False),
            sa.Column("reason", sa.String(250), nullable=False),
            sa.Column("created_by_user_id", sa.String(36), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("idx_scheduled_stops_machine_range", "scheduled_stops", ["machine_id", "start_at", "end_at"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("scheduled_stops"):
        op.drop_table("scheduled_stops")
    if inspector.has_table("machine_availability_events"):
        op.drop_table("machine_availability_events")
    if inspector.has_table("machines"):
        op.drop_table("machines")
