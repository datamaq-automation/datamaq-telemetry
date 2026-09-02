"""backfill potencia aparente y factor de potencia con S = V*I

Recalcula `apparent_power_*` y `power_factor_*` sobre las lecturas ya persistidas.

Las filas históricas tienen esas columnas en NULL (el firmware compacto nunca las
publicó y la ingesta no las derivaba) o con la semántica vieja de `hypot(P, Q)`
proveniente del path de agregación. Ambos casos se reescriben con `S = V·I`, que es
la definición que usa el backend desde ahora.

El SQL es deliberadamente portable entre MySQL y SQLite: los tests de migraciones
corren sobre SQLite, que no tiene `GREATEST`/`LEAST`, mientras que MySQL no tiene
`MIN`/`MAX` escalares de dos argumentos. El acotado del factor de potencia se hace
con `CASE WHEN`.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-09-01 21:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d0e1f2a3b4"
down_revision: str | Sequence[str] | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLA = "telemetry_instantaneous"
FASES = ("r", "s", "t")
TAMANIO_LOTE = 50_000


def _tiene_columna(inspector: sa.Inspector, tabla: str, columna: str) -> bool:
    if not inspector.has_table(tabla):
        return False
    return any(c["name"] == columna for c in inspector.get_columns(tabla))


def _acotar(expresion: str) -> str:
    """Acota una expresión al rango [-1, 1] sin funciones específicas de motor."""
    return f"CASE WHEN {expresion} > 1 THEN 1.0 WHEN {expresion} < -1 THEN -1.0 ELSE ROUND({expresion}, 2) END"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLA):
        return

    columnas_necesarias = ["total_active_power", "total_apparent_power", "total_power_factor"]
    for f in FASES:
        columnas_necesarias += [
            f"voltage_{f}",
            f"current_{f}",
            f"active_power_{f}",
            f"apparent_power_{f}",
            f"power_factor_{f}",
        ]
    if not all(_tiene_columna(inspector, TABLA, c) for c in columnas_necesarias):
        return

    rango = bind.execute(sa.text(f"SELECT MIN(id), MAX(id) FROM {TABLA}")).first()
    if rango is None or rango[0] is None:
        return
    id_min, id_max = int(rango[0]), int(rango[1])

    # Se recorre por rangos de id en vez de un UPDATE masivo: `UPDATE ... LIMIT` no es
    # portable a SQLite y un solo UPDATE bloquearía la tabla en producción.
    for lote_desde in range(id_min, id_max + 1, TAMANIO_LOTE):
        acotado = {"lo": lote_desde, "hi": lote_desde + TAMANIO_LOTE}

        for f in FASES:
            bind.execute(
                sa.text(
                    f"UPDATE {TABLA} SET apparent_power_{f} = ROUND(ABS(voltage_{f}) * ABS(current_{f}), 2) "
                    f"WHERE id >= :lo AND id < :hi AND voltage_{f} IS NOT NULL AND current_{f} IS NOT NULL"
                ),
                acotado,
            )
            # `* 1.0` fuerza división flotante: SQLite divide como enteros cuando ambos
            # operandos lo son (MySQL no), y 300/400 daba 0 en vez de 0.75.
            cociente = f"(active_power_{f} * 1.0) / apparent_power_{f}"
            bind.execute(
                sa.text(
                    f"UPDATE {TABLA} SET power_factor_{f} = {_acotar(cociente)} "
                    f"WHERE id >= :lo AND id < :hi AND active_power_{f} IS NOT NULL "
                    f"AND apparent_power_{f} IS NOT NULL AND apparent_power_{f} > 0"
                ),
                acotado,
            )

        bind.execute(
            sa.text(
                f"UPDATE {TABLA} SET total_apparent_power = ROUND("
                "COALESCE(apparent_power_r, 0) + COALESCE(apparent_power_s, 0) + COALESCE(apparent_power_t, 0), 2) "
                "WHERE id >= :lo AND id < :hi AND (apparent_power_r IS NOT NULL "
                "OR apparent_power_s IS NOT NULL OR apparent_power_t IS NOT NULL)"
            ),
            acotado,
        )
        cociente_total = "(total_active_power * 1.0) / total_apparent_power"
        bind.execute(
            sa.text(
                f"UPDATE {TABLA} SET total_power_factor = {_acotar(cociente_total)} "
                "WHERE id >= :lo AND id < :hi AND total_active_power IS NOT NULL "
                "AND total_apparent_power IS NOT NULL AND total_apparent_power > 0"
            ),
            acotado,
        )


def downgrade() -> None:
    """No-op deliberado.

    Es una migración de datos: los valores previos eran NULL o una aproximación por
    `hypot(P, Q)` que no se puede reconstruir sin recalcularla. Revertir a NULL
    perdería también los valores que sí publicó el firmware.
    """
