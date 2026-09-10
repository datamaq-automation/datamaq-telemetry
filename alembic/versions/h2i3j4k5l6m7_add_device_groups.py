"""add device_groups and device_group_members

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-09-10 19:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "h2i3j4k5l6m7"
down_revision: str | Sequence[str] | None = "g1h2i3j4k5l6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table("device_groups"):
        op.create_table(
            "device_groups",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("facility_id", sa.String(36), sa.ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(150), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("idx_device_group_facility", "device_groups", ["facility_id"])

    if not inspector.has_table("device_group_members"):
        op.create_table(
            "device_group_members",
            sa.Column(
                "group_id", sa.String(36), sa.ForeignKey("device_groups.id", ondelete="CASCADE"), primary_key=True
            ),
            sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("device_group_members"):
        op.drop_table("device_group_members")
    if inspector.has_table("device_groups"):
        op.drop_table("device_groups")
