"""mqtt_consumo_horario: mensajes y bytes MQTT por equipo y hora

Revision ID: d5f2a9c1e7b3
Revises: c4e8a1d2f6b9
Create Date: 2026-10-29 12:00:00.000000

Persiste lo que ya se loguea como ``mqtt_mensaje_recibido`` (#93): cuántos mensajes y cuántos bytes
de payload llegaron por equipo y hora UTC. Mide lo que llega al servidor, no el consumo del chip.
Reversible: el downgrade borra la tabla (los agregados se pierden, no hay datos de origen que tocar).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d5f2a9c1e7b3"
down_revision: str | Sequence[str] | None = "c4e8a1d2f6b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mqtt_consumo_horario",
        sa.Column("uid", sa.String(length=32), nullable=False),
        sa.Column("hora", sa.DateTime(), nullable=False),
        sa.Column("mensajes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("bytes_payload", sa.BigInteger(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("uid", "hora"),
    )


def downgrade() -> None:
    op.drop_table("mqtt_consumo_horario")
