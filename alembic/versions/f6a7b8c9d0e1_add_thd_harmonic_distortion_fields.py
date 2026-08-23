"""add harmonic distortion THD fields to telemetry_instantaneous

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-22 22:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: str | Sequence[str] | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tiene_columna(inspector: sa.Inspector, tabla: str, columna: str) -> bool:
    if not inspector.has_table(tabla):
        return False
    return any(c["name"] == columna for c in inspector.get_columns(tabla))


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("telemetry_instantaneous"):
        columnas_thd = [
            ("thd_v_r", sa.Numeric(5, 2)),
            ("thd_i_r", sa.Numeric(5, 2)),
            ("thd_v_s", sa.Numeric(5, 2)),
            ("thd_i_s", sa.Numeric(5, 2)),
            ("thd_v_t", sa.Numeric(5, 2)),
            ("thd_i_t", sa.Numeric(5, 2)),
            ("thd_v_promedio_porcentaje", sa.Numeric(5, 2)),
            ("thd_i_total_porcentaje", sa.Numeric(5, 2)),
        ]
        for nombre_col, tipo_col in columnas_thd:
            if not _tiene_columna(inspector, "telemetry_instantaneous", nombre_col):
                op.add_column("telemetry_instantaneous", sa.Column(nombre_col, tipo_col, nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("telemetry_instantaneous"):
        columnas = (
            "thd_i_total_porcentaje",
            "thd_v_promedio_porcentaje",
            "thd_i_t",
            "thd_v_t",
            "thd_i_s",
            "thd_v_s",
            "thd_i_r",
            "thd_v_r",
        )
        for col in columnas:
            if _tiene_columna(inspector, "telemetry_instantaneous", col):
                op.drop_column("telemetry_instantaneous", col)
