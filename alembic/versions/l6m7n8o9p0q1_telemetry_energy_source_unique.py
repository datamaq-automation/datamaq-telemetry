"""telemetry_energy: columna source y unicidad (device_id, recorded_at)

WP2 (D1, D2, D3, H2): acc y energyio publican el mismo timestamp cuando
un medidor manda los dos subtópicos, y hoy ambos terminan como filas
separadas (el medidor de la organización invitado tenía 123 363 filas
duplicadas sobre 246 726, el 50%).

Esta migración:
1. Agrega `source` (nullable) para rastrear qué subtópico escribió cada
   fila desde ahora en adelante (NULL en filas anteriores a este cambio,
   que no lo rastreaban).
2. Agrega un índice único (device_id, recorded_at) para que la ingesta
   no pueda volver a duplicar un instante — ver guardar_energia (WP2).

D2 (nada se borra): esta migración no borra ni mueve ninguna fila
existente. Las duplicadas históricas (device_id, recorded_at repetido)
quedan como están; el índice único solo rige inserciones futuras. Por
eso el paso 2 falla si hay duplicados sin resolver — ver la nota en
upgrade() sobre cómo se resuelven antes de aplicar esto en producción.

Revision ID: l6m7n8o9p0q1
Revises: k5l6m7n8o9p0
Create Date: 2026-09-13 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "l6m7n8o9p0q1"
down_revision: str | Sequence[str] | None = "k5l6m7n8o9p0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLA = "telemetry_energy"
COLUMNA_SOURCE = "source"
INDICE_UNICO = "uq_energy_dev_time"


def _tiene_columna(inspector: sa.Inspector, tabla: str, columna: str) -> bool:
    if not inspector.has_table(tabla):
        return False
    return any(c["name"] == columna for c in inspector.get_columns(tabla))


def _tiene_indice(inspector: sa.Inspector, tabla: str, nombre: str) -> bool:
    if not inspector.has_table(tabla):
        return False
    return any(ix["name"] == nombre for ix in inspector.get_indexes(tabla))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLA):
        return

    if not _tiene_columna(inspector, TABLA, COLUMNA_SOURCE):
        op.add_column(TABLA, sa.Column(COLUMNA_SOURCE, sa.String(16), nullable=True))

    if not _tiene_indice(inspector, TABLA, INDICE_UNICO):
        # Si esto falla con un error de duplicado (device_id, recorded_at), hay
        # filas históricas a resolver antes de correr esta migración en ese
        # entorno: identificar los pares con
        #   SELECT device_id, recorded_at, COUNT(*) FROM telemetry_energy
        #   GROUP BY 1, 2 HAVING COUNT(*) > 1
        # y decidir cuál de las dos conservar (D3) antes de reintentar. No se
        # automatiza acá porque, como se verificó contra datos reales, no hay
        # un criterio confiable para adivinar cuál fila viene de qué fuente
        # a partir de los valores ya guardados (ver docs/adr-001 y la
        # discusión de D1/D3 en el plan de mejoras de base de datos).
        op.create_index(INDICE_UNICO, TABLA, ["device_id", "recorded_at"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLA):
        return

    if _tiene_indice(inspector, TABLA, INDICE_UNICO):
        op.drop_index(INDICE_UNICO, table_name=TABLA)

    if _tiene_columna(inspector, TABLA, COLUMNA_SOURCE):
        op.drop_column(TABLA, COLUMNA_SOURCE)
