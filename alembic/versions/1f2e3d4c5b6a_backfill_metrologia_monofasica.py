"""backfill de metrología monofásica: anula columnas trifásicas derivadas

En instalaciones monofásicas (1P2W) los tres bornes de tensión están en paralelo
(sin desfasaje de 120°), por lo que las métricas trifásicas derivadas carecen de
significado físico. Esta migración anula en las lecturas ya persistidas las cuatro
columnas derivadas que dependen de la hipótesis trifásica:

- ``desbalance_tension_porcentaje``
- ``current_n``
- ``voltage_linea_V``
- ``tension_neutro_estimada``

Se identifican como monofásicos los dispositivos cuyo tipo de instalación es ``1P2W``
o cuya configuración ``phases_with_ct`` lista una única fase (sin coma y no vacía).
Una instalación Aron (dos fases con TI) sigue siendo trifásica.

El SQL es portable entre MySQL y SQLite: ``UPPER``/``TRIM``/``IN`` y ``NOT LIKE``
están disponibles en ambos motores. La subconsulta lee de ``devices`` mientras la
actualización toca ``telemetry_instantaneous``, por lo que no hay conflicto de tabla.

Revision ID: 1f2e3d4c5b6a
Revises: c9d0e1f2a3b4
Create Date: 2026-09-01 23:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1f2e3d4c5b6a"
down_revision: str | Sequence[str] | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLA_LECTURAS = "telemetry_instantaneous"
TABLA_DISPOSITIVOS = "devices"
COLUMNAS_DERIVADAS = (
    "desbalance_tension_porcentaje",
    "current_n",
    "voltage_linea_V",
    "tension_neutro_estimada",
)

PREDICADO_MONOFASICO = (
    "UPPER(TRIM(installation_type)) = '1P2W' "
    "OR (phases_with_ct IS NOT NULL AND TRIM(phases_with_ct) <> '' "
    "AND phases_with_ct NOT LIKE '%,%')"
)


def _tiene_columna(inspector: sa.Inspector, tabla: str, columna: str) -> bool:
    if not inspector.has_table(tabla):
        return False
    return any(c["name"] == columna for c in inspector.get_columns(tabla))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table(TABLA_LECTURAS) or not inspector.has_table(TABLA_DISPOSITIVOS):
        return

    if not all(_tiene_columna(inspector, TABLA_LECTURAS, c) for c in COLUMNAS_DERIVADAS):
        return
    if not _tiene_columna(inspector, TABLA_DISPOSITIVOS, "installation_type"):
        return
    if not _tiene_columna(inspector, TABLA_DISPOSITIVOS, "phases_with_ct"):
        return

    asignaciones = ", ".join(f"{c} = NULL" for c in COLUMNAS_DERIVADAS)
    bind.execute(
        sa.text(
            f"UPDATE {TABLA_LECTURAS} SET {asignaciones} "
            f"WHERE device_id IN (SELECT id FROM {TABLA_DISPOSITIVOS} "
            f"WHERE {PREDICADO_MONOFASICO})"
        )
    )


def downgrade() -> None:
    """No-op deliberado.

    Es una migración de datos que anula columnas derivadas: los valores previos no se
    pueden reconstruir sin recalcularlos. Revertir a NULL no restauraría los datos
    trifásicos originales.
    """
