"""add characterization_campaigns y campaign_samples

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-09-04 11:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3a4b5c6d7e8"
down_revision: str | Sequence[str] | None = "e2f3a4b5c6d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table("characterization_campaigns"):
        op.create_table(
            "characterization_campaigns",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
            sa.Column("load_id", sa.String(36), sa.ForeignKey("loads.id", ondelete="CASCADE"), nullable=True),
            sa.Column("campaign_type", sa.String(20), nullable=False),
            sa.Column("state", sa.String(20), nullable=False, server_default="EN_CURSO"),
            sa.Column("start_at", sa.DateTime(), nullable=False),
            sa.Column("planned_end_at", sa.DateTime(), nullable=False),
            sa.Column("end_at", sa.DateTime(), nullable=True),
            sa.Column("baseline_w", sa.Numeric(10, 2), nullable=True),
            sa.Column("baseline_var", sa.Numeric(10, 2), nullable=True),
            sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("discard_reason", sa.String(30), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_by_user_id", sa.String(36), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("idx_campaigns_device_state", "characterization_campaigns", ["device_id", "state"])

    if not inspector.has_table("campaign_samples"):
        op.create_table(
            "campaign_samples",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column(
                "campaign_id",
                sa.String(36),
                sa.ForeignKey("characterization_campaigns.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("recorded_at", sa.DateTime(), nullable=False),
            sa.Column("active_power_w", sa.Numeric(12, 2), nullable=True),
            sa.Column("reactive_power_var", sa.Numeric(12, 2), nullable=True),
            sa.Column("apparent_power_va", sa.Numeric(12, 2), nullable=True),
            sa.Column("power_factor", sa.Numeric(4, 3), nullable=True),
            sa.Column("voltage_v", sa.Numeric(6, 2), nullable=True),
            sa.Column("current_a", sa.Numeric(8, 2), nullable=True),
            # Idempotencia ante el redelivery de MQTT QoS 1. Va dentro del CREATE TABLE
            # porque SQLite —donde corre la suite de migraciones— no admite ALTER de
            # constraints.
            sa.UniqueConstraint("campaign_id", "recorded_at", name="uq_campaign_samples_time"),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("campaign_samples"):
        op.drop_table("campaign_samples")
    if inspector.has_table("characterization_campaigns"):
        op.drop_table("characterization_campaigns")
