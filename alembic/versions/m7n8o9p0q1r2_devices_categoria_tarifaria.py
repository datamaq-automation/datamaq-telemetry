"""devices: columnas categoria_tarifaria y penalizacion_reactiva_aplica

D-11: estos dos campos ya existían en la entidad de dominio (Dispositivo) y en el
DTO de la API con default "T2"/True, y `PATCH /api/dispositivos/{id}` los acepta
— pero nunca fueron columnas reales de `devices`. `DispositivosRepository._to_entity`
solo mapea `installation_type`/`phases_with_ct`; nada mapea categoria_tarifaria ni
penalizacion_reactiva_aplica. Resultado: cualquier intento de setearlos era un
no-op silencioso — la siguiente lectura siempre devolvía el default de la entidad,
nunca lo persistido (porque no había nada persistido).

Se descubrió investigando D-11: la exención de reactiva dependía en la práctica
solo del atajo por "es monofásico" en _evaluar_abstencion_enre, porque
categoria_tarifaria jamás podía ser otra cosa que "T2" en una respuesta real.

Revision ID: m7n8o9p0q1r2
Revises: l6m7n8o9p0q1
Create Date: 2026-09-13 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "m7n8o9p0q1r2"
down_revision: str | Sequence[str] | None = "l6m7n8o9p0q1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLA = "devices"


def _tiene_columna(inspector: sa.Inspector, tabla: str, columna: str) -> bool:
    if not inspector.has_table(tabla):
        return False
    return any(c["name"] == columna for c in inspector.get_columns(tabla))


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(TABLA):
        return
    if not _tiene_columna(inspector, TABLA, "categoria_tarifaria"):
        op.add_column(
            TABLA,
            sa.Column("categoria_tarifaria", sa.String(10), nullable=False, server_default="T2"),
        )
    if not _tiene_columna(inspector, TABLA, "penalizacion_reactiva_aplica"):
        op.add_column(
            TABLA,
            sa.Column("penalizacion_reactiva_aplica", sa.Boolean(), nullable=False, server_default=sa.true()),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(TABLA):
        return
    if _tiene_columna(inspector, TABLA, "penalizacion_reactiva_aplica"):
        op.drop_column(TABLA, "penalizacion_reactiva_aplica")
    if _tiene_columna(inspector, TABLA, "categoria_tarifaria"):
        op.drop_column(TABLA, "categoria_tarifaria")
