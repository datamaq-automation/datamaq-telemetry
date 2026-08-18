"""reconcile legacy

Revision ID: 2e6e9c693368
Revises: 209ce0774d59
Create Date: 2026-08-17 21:07:22.588493

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2e6e9c693368"
down_revision: str | Sequence[str] | None = "209ce0774d59"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tiene_columna(inspector: sa.Inspector, tabla: str, columna: str) -> bool:
    if not inspector.has_table(tabla):
        return False
    return any(c["name"] == columna for c in inspector.get_columns(tabla))


def _tiene_indice(inspector: sa.Inspector, tabla: str, indice: str) -> bool:
    if not inspector.has_table(tabla):
        return False
    return any(i["name"] == indice for i in inspector.get_indexes(tabla))


def _crear_indice_si_falta(inspector: sa.Inspector, tabla: str, indice: str, columnas: list[str]) -> None:
    if not _tiene_indice(inspector, tabla, indice):
        op.create_index(indice, tabla, columnas)


def _dropar_indice_si_existe(inspector: sa.Inspector, tabla: str, indice: str) -> None:
    if _tiene_indice(inspector, tabla, indice):
        op.drop_index(indice, table_name=tabla)


def upgrade() -> None:
    """Reconcilia una BD legacy creada antes de que el ORM incluyera role/plan_id/índices."""
    inspector = sa.inspect(op.get_bind())

    # Crítico: users.role (bloquea login/auth). Rellena filas existentes con 'operador'.
    if not _tiene_columna(inspector, "users", "role"):
        op.add_column("users", sa.Column("role", sa.String(20), nullable=False, server_default="operador"))

    # Crítico: organizations.plan_id (FK a plans.id). batch_alter_table = portable SQLite/MySQL.
    if not _tiene_columna(inspector, "organizations", "plan_id"):
        with op.batch_alter_table("organizations") as batch_op:
            batch_op.add_column(sa.Column("plan_id", sa.String(36), nullable=True))
            batch_op.create_foreign_key(
                "fk_organizations_plan_id",
                "plans",
                ["plan_id"],
                ["id"],
                ondelete="SET NULL",
            )

    # Menor: device_status_logs.wifi_calidad (drift defensivo; puede no existir en legacies muy antiguos).
    if not _tiene_columna(inspector, "device_status_logs", "wifi_calidad"):
        op.add_column("device_status_logs", sa.Column("wifi_calidad", sa.Integer(), nullable=True))

    # Menor: índices compuestos definidos en __table_args__ del ORM.
    _crear_indice_si_falta(
        inspector, "telemetry_instantaneous", "idx_telemetry_inst_dev_time", ["device_id", "recorded_at"]
    )
    _crear_indice_si_falta(inspector, "telemetry_instantaneous", "idx_telemetry_inst_time", ["recorded_at"])
    _crear_indice_si_falta(inspector, "telemetry_energy", "idx_telemetry_energy_dev_time", ["device_id", "recorded_at"])
    _crear_indice_si_falta(inspector, "telemetry_energy", "idx_telemetry_energy_time", ["recorded_at"])
    _crear_indice_si_falta(inspector, "device_status_logs", "idx_device_status_dev_time", ["device_id", "recorded_at"])
    _crear_indice_si_falta(inspector, "device_status_logs", "idx_device_status_time", ["recorded_at"])
    _crear_indice_si_falta(inspector, "device_alerts", "idx_alerts_dev_resolved", ["device_id", "is_resolved"])
    _crear_indice_si_falta(inspector, "device_alerts", "idx_alerts_resolved_purge", ["is_resolved", "resolved_at"])


def downgrade() -> None:
    """Revierte los cambios de reconciliación (índices, plan_id, role)."""
    inspector = sa.inspect(op.get_bind())

    _dropar_indice_si_existe(inspector, "telemetry_instantaneous", "idx_telemetry_inst_dev_time")
    _dropar_indice_si_existe(inspector, "telemetry_instantaneous", "idx_telemetry_inst_time")
    _dropar_indice_si_existe(inspector, "telemetry_energy", "idx_telemetry_energy_dev_time")
    _dropar_indice_si_existe(inspector, "telemetry_energy", "idx_telemetry_energy_time")
    _dropar_indice_si_existe(inspector, "device_status_logs", "idx_device_status_dev_time")
    _dropar_indice_si_existe(inspector, "device_status_logs", "idx_device_status_time")
    _dropar_indice_si_existe(inspector, "device_alerts", "idx_alerts_dev_resolved")
    _dropar_indice_si_existe(inspector, "device_alerts", "idx_alerts_resolved_purge")

    if _tiene_columna(inspector, "organizations", "plan_id"):
        with op.batch_alter_table("organizations") as batch_op:
            batch_op.drop_constraint("fk_organizations_plan_id", type_="foreignkey")
            batch_op.drop_column("plan_id")

    if _tiene_columna(inspector, "device_status_logs", "wifi_calidad"):
        op.drop_column("device_status_logs", "wifi_calidad")

    if _tiene_columna(inspector, "users", "role"):
        op.drop_column("users", "role")
