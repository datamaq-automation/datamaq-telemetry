"""add es_dato_confiable flag to telemetry_instantaneous

Revision ID: w7x8y9z0a1b2
Revises: v6w7x8y9z0a1
Create Date: 2026-09-27 18:58:00.000000

Marca datos históricos como no confiables cuando el dispositivo estuvo en periodo de diagnóstico (TI invertidos).
San Martín (c91713f1-0621-4a33-9279-c5327a317d96): 2026-09-27 00:00 a 17:00.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "w7x8y9z0a1b2"
down_revision: str | Sequence[str] | None = "v6w7x8y9z0a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tiene_columna(inspector: sa.Inspector, tabla: str, columna: str) -> bool:
    if not inspector.has_table(tabla):
        return False
    return any(c["name"] == columna for c in inspector.get_columns(tabla))


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("telemetry_instantaneous"):
        if not _tiene_columna(inspector, "telemetry_instantaneous", "es_dato_confiable"):
            op.add_column(
                "telemetry_instantaneous",
                sa.Column("es_dato_confiable", sa.Boolean(), server_default="1", nullable=False),
            )
            # Marcar periodo de diagnóstico de San Martín (TI invertidos/mal orden)
            # Dispositivo: c91713f1-0621-4a33-9279-c5327a317d96
            # Período: 2026-09-27 00:00:00 a 2026-09-27 17:00:00 (2885 registros)
            op.execute(
                "UPDATE telemetry_instantaneous "
                "SET es_dato_confiable = 0 "
                "WHERE device_id = 'c91713f1-0621-4a33-9279-c5327a317d96' "
                "  AND recorded_at < '2026-09-27 17:00:00'"
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("telemetry_instantaneous"):
        if _tiene_columna(inspector, "telemetry_instantaneous", "es_dato_confiable"):
            op.drop_column("telemetry_instantaneous", "es_dato_confiable")
