"""initial schema

Revision ID: 209ce0774d59
Revises:
Create Date: 2026-08-17 21:07:21.883280

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "209ce0774d59"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea el esquema completo desde el ORM (equivalente a Base.metadata.create_all)."""
    op.create_table(
        "plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("monthly_price_ars", sa.Numeric(12, 2), nullable=False),
        sa.Column("visibility", sa.String(20), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("granularity_minutes", sa.Integer(), nullable=False),
        sa.Column("max_devices", sa.Integer(), nullable=False),
        sa.Column("notification_channels", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "organizations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("plan_id", sa.String(36), sa.ForeignKey("plans.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tax_id", sa.String(50), nullable=True),
        sa.Column("contact_email", sa.String(120), nullable=True),
        sa.Column("contact_phone", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "facilities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("address", sa.String(255), nullable=True),
        sa.Column("latitude", sa.Numeric(10, 8), nullable=True),
        sa.Column("longitude", sa.Numeric(11, 8), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "devices",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("facilities.id", ondelete="SET NULL"), nullable=True),
        sa.Column("device_uid", sa.String(64), nullable=False, unique=True),
        sa.Column("serial_number", sa.String(64), nullable=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("model", sa.String(50), nullable=False),
        sa.Column("hw_version", sa.String(50), nullable=True),
        sa.Column("fw_version", sa.String(50), nullable=True),
        sa.Column("tag_location", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "telemetry_instantaneous",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.Column("voltage_r", sa.Numeric(6, 2), nullable=True),
        sa.Column("current_r", sa.Numeric(6, 2), nullable=True),
        sa.Column("active_power_r", sa.Numeric(10, 2), nullable=True),
        sa.Column("reactive_power_r", sa.Numeric(10, 2), nullable=True),
        sa.Column("apparent_power_r", sa.Numeric(10, 2), nullable=True),
        sa.Column("power_factor_r", sa.Numeric(4, 2), nullable=True),
        sa.Column("voltage_s", sa.Numeric(6, 2), nullable=True),
        sa.Column("current_s", sa.Numeric(6, 2), nullable=True),
        sa.Column("active_power_s", sa.Numeric(10, 2), nullable=True),
        sa.Column("reactive_power_s", sa.Numeric(10, 2), nullable=True),
        sa.Column("apparent_power_s", sa.Numeric(10, 2), nullable=True),
        sa.Column("power_factor_s", sa.Numeric(4, 2), nullable=True),
        sa.Column("voltage_t", sa.Numeric(6, 2), nullable=True),
        sa.Column("current_t", sa.Numeric(6, 2), nullable=True),
        sa.Column("active_power_t", sa.Numeric(10, 2), nullable=True),
        sa.Column("reactive_power_t", sa.Numeric(10, 2), nullable=True),
        sa.Column("apparent_power_t", sa.Numeric(10, 2), nullable=True),
        sa.Column("power_factor_t", sa.Numeric(4, 2), nullable=True),
        sa.Column("total_active_power", sa.Numeric(12, 2), nullable=True),
        sa.Column("total_reactive_power", sa.Numeric(12, 2), nullable=True),
        sa.Column("total_apparent_power", sa.Numeric(12, 2), nullable=True),
        sa.Column("total_power_factor", sa.Numeric(4, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("idx_telemetry_inst_dev_time", "telemetry_instantaneous", ["device_id", "recorded_at"])
    op.create_index("idx_telemetry_inst_time", "telemetry_instantaneous", ["recorded_at"])

    op.create_table(
        "telemetry_energy",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.Column("net_active_energy_kwh", sa.Numeric(14, 3), nullable=True),
        sa.Column("net_reactive_energy_kvarh", sa.Numeric(14, 3), nullable=True),
        sa.Column("imported_active_energy_kwh", sa.Numeric(14, 3), nullable=True),
        sa.Column("exported_active_energy_kwh", sa.Numeric(14, 3), nullable=True),
        sa.Column("imported_reactive_energy_kvarh", sa.Numeric(14, 3), nullable=True),
        sa.Column("exported_reactive_energy_kvarh", sa.Numeric(14, 3), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("idx_telemetry_energy_dev_time", "telemetry_energy", ["device_id", "recorded_at"])
    op.create_index("idx_telemetry_energy_time", "telemetry_energy", ["recorded_at"])

    op.create_table(
        "device_status_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.Column("wifi_rssi_dbm", sa.Integer(), nullable=True),
        sa.Column("wifi_calidad", sa.Integer(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("uptime_seconds", sa.BigInteger(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("idx_device_status_dev_time", "device_status_logs", ["device_id", "recorded_at"])
    op.create_index("idx_device_status_time", "device_status_logs", ["recorded_at"])

    op.create_table(
        "device_alerts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "device_id", sa.String(36), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
        ),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.Enum("INFO", "WARNING", "CRITICAL", name="alert_severity"), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("is_resolved", sa.Boolean(), nullable=False),
        sa.Column("triggered_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
    )
    op.create_index("idx_alerts_dev_resolved", "device_alerts", ["device_id", "is_resolved"])
    op.create_index("idx_alerts_resolved_purge", "device_alerts", ["is_resolved", "resolved_at"])

    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(150), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    """Elimina todas las tablas en orden inverso."""
    for tabla in [
        "users",
        "device_alerts",
        "device_status_logs",
        "telemetry_energy",
        "telemetry_instantaneous",
        "devices",
        "facilities",
        "organizations",
        "plans",
    ]:
        op.drop_table(tabla)
