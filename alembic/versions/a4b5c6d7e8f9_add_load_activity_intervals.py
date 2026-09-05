"""add load_activity_intervals

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-09-04 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4b5c6d7e8f9"
down_revision: str | Sequence[str] | None = "f3a4b5c6d7e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table("load_activity_intervals"):
        op.create_table(
            "load_activity_intervals",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
            # Nulo = NO_ATRIBUIDO: actividad real que no se pudo imputar a ninguna carga.
            sa.Column("load_id", sa.String(36), sa.ForeignKey("loads.id", ondelete="CASCADE"), nullable=True),
            sa.Column("start_at", sa.DateTime(), nullable=False),
            sa.Column("end_at", sa.DateTime(), nullable=False),
            sa.Column("avg_power_w", sa.Numeric(12, 2), nullable=True),
            sa.Column("delta_reactive_var", sa.Numeric(12, 2), nullable=True),
            sa.Column("energy_kwh", sa.Numeric(12, 4), nullable=True),
            sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
            sa.Column("origin", sa.String(20), nullable=False, server_default="REGLA"),
            sa.Column("corrected_by_user_id", sa.String(36), nullable=True),
            sa.Column("corrected_at", sa.DateTime(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            # Idempotencia del batch: re-correr una ventana actualiza en vez de duplicar.
            # Inline y no por ALTER porque SQLite —donde corre la suite— no lo soporta.
            sa.UniqueConstraint("device_id", "start_at", "end_at", name="uq_load_intervals_window"),
        )
        op.create_index("idx_load_intervals_load_time", "load_activity_intervals", ["load_id", "start_at"])
        op.create_index("idx_load_intervals_device_time", "load_activity_intervals", ["device_id", "start_at"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("load_activity_intervals"):
        op.drop_table("load_activity_intervals")
