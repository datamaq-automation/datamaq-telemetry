"""create telemetria_anomalias and dispositivo_diagnosticos tables

Revision ID: u5v6w7x8y9z0
Revises: t4u5v6w7x8y9
Create Date: 2026-09-27 18:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "u5v6w7x8y9z0"
down_revision: str | Sequence[str] | None = "t4u5v6w7x8y9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. Tabla telemetria_anomalias: registro de flags de coherencia baja
    if not inspector.has_table("telemetria_anomalias"):
        op.create_table(
            "telemetria_anomalias",
            sa.Column("id", sa.BigInteger(), nullable=False, primary_key=True, autoincrement=True),
            sa.Column("device_id", sa.String(36), nullable=False),
            sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "error_s",
                sa.Float(),
                nullable=False,
                comment="Error % entre S medida y S teórica",
            ),
            sa.Column(
                "flag_tipo",
                sa.Enum("coherencia_baja", "degradacion", "otros", name="anomalia_tipo"),
                nullable=False,
            ),
            sa.Column("contador_consecutivos", sa.Integer(), nullable=False, default=1),
            sa.Column(
                "estado",
                sa.Enum("active", "resolved", name="anomalia_estado"),
                nullable=False,
                default="active",
            ),
            sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        )
        op.create_index("idx_anomalias_device_recorded", "telemetria_anomalias", ["device_id", "recorded_at"])
        op.create_index("idx_anomalias_estado", "telemetria_anomalias", ["estado"])

    # 2. Tabla dispositivo_diagnosticos: histórico de diagnósticos TI
    if not inspector.has_table("dispositivo_diagnosticos"):
        op.create_table(
            "dispositivo_diagnosticos",
            sa.Column("id", sa.BigInteger(), nullable=False, primary_key=True, autoincrement=True),
            sa.Column("device_id", sa.String(36), nullable=False),
            sa.Column("ejecutado_en", sa.DateTime(timezone=True), nullable=False),
            sa.Column("config_actual", sa.String(50), nullable=True, comment="R,S,T o S,R,T (formato)"),
            sa.Column("config_actual_invertido", sa.Boolean(), nullable=True),
            sa.Column("top_candidato", sa.String(50), nullable=True),
            sa.Column("top_candidato_invertido", sa.Boolean(), nullable=True),
            sa.Column("top_score", sa.Float(), nullable=True),
            sa.Column("registros_analizados", sa.Integer(), nullable=True),
            sa.Column("mismatch", sa.Boolean(), nullable=True, comment="true si top != actual"),
            sa.Column("alerta_enviada", sa.Boolean(), nullable=False, default=False),
            sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        )
        op.create_index("idx_diagnosticos_device_ejecutado", "dispositivo_diagnosticos", ["device_id", "ejecutado_en"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Eliminar tablas en orden inverso (FK primero)
    if inspector.has_table("dispositivo_diagnosticos"):
        op.drop_table("dispositivo_diagnosticos")

    if inspector.has_table("telemetria_anomalias"):
        op.drop_table("telemetria_anomalias")
