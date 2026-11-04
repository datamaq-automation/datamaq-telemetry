"""devices: medidor_id para equipos con varios medidores (Pro15)

Revision ID: f1a2b3c4d5e6
Revises: e8a1f3c2b4d6
Create Date: 2026-11-03 12:00:00.000000

Un Pro15 es una MAC con dos medidores internos (id 0 y 1). Hasta ahora `devices.device_uid` era único,
así que una MAC era un solo dispositivo. Ahora la unicidad pasa a (device_uid, medidor_id).

`medidor_id` es NOT NULL DEFAULT 0: en MySQL un UNIQUE admite varias filas con NULL, así que no puede
ser nullable. Los equipos existentes quedan en 0 y su comportamiento no cambia.

SQLite no permite ALTER de restricciones: por eso todo va dentro de `batch_alter_table`, con una
convención de nombres que da nombre a la UNIQUE sin nombre que crea la migración inicial.

Downgrade: solo es seguro si no hay dos filas con la misma MAC (un Pro15 con dos medidores lo impide).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "e8a1f3c2b4d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLA = "devices"
UNIQUE_NUEVA = "uq_devices_uid_medidor"
UNIQUE_ANTIGUA = "uq_devices_device_uid"
INDICE_MAC = "ix_devices_device_uid"
NAMING_CONVENTION = {
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ix": "ix_%(table_name)s_%(column_0_name)s",
}


def _unicos_solo_device_uid(inspector: sa.Inspector) -> set[str]:
    """Nombres de la UNIQUE(device_uid) actual.

    MySQL la reporta con su nombre de índice. SQLite la tiene sin nombre: con NAMING_CONVENTION el batch
    la nombra UNIQUE_ANTIGUA, así que ese es el nombre a borrar.
    """
    nombres: set[str] = set()
    for uq in inspector.get_unique_constraints(TABLA):
        if list(uq.get("column_names") or []) == ["device_uid"]:
            nombres.add(uq.get("name") or UNIQUE_ANTIGUA)
    for ix in inspector.get_indexes(TABLA):
        if ix.get("unique") and list(ix.get("column_names") or []) == ["device_uid"] and ix.get("name"):
            nombres.add(ix["name"])
    return nombres


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(TABLA):
        return
    columnas = {c["name"] for c in inspector.get_columns(TABLA)}
    unicos_antiguos = _unicos_solo_device_uid(inspector)
    existentes_uq = {uq.get("name") for uq in inspector.get_unique_constraints(TABLA)}
    indices = {ix["name"] for ix in inspector.get_indexes(TABLA)}

    with op.batch_alter_table(TABLA, naming_convention=NAMING_CONVENTION) as batch:
        if "medidor_id" not in columnas:
            batch.add_column(sa.Column("medidor_id", sa.Integer(), nullable=False, server_default="0"))
        for nombre in sorted(unicos_antiguos):
            batch.drop_constraint(nombre, type_="unique")
        if UNIQUE_NUEVA not in existentes_uq:
            batch.create_unique_constraint(UNIQUE_NUEVA, ["device_uid", "medidor_id"])
        # Índice no único para las búsquedas por MAC (antes lo hacía el índice único).
        if INDICE_MAC not in indices:
            batch.create_index(INDICE_MAC, ["device_uid"], unique=False)


def downgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table(TABLA):
        return
    # Con varios medidores por MAC, volver a UNIQUE(device_uid) perdería filas. Se falla antes de tocar nada.
    duplicadas = (
        op.get_bind()
        .execute(sa.text("SELECT device_uid FROM devices GROUP BY device_uid HAVING COUNT(*) > 1 LIMIT 5"))
        .fetchall()
    )
    if duplicadas:
        uids = ", ".join(str(fila[0]) for fila in duplicadas)
        raise RuntimeError(
            "downgrade f1a2b3c4d5e6 abortado: hay device_uid con más de un medidor "
            f"({uids}). Eliminar o reasignar esas filas antes de volver atrás."
        )

    inspector = sa.inspect(op.get_bind())
    columnas = {c["name"] for c in inspector.get_columns(TABLA)}
    existentes_uq = {uq.get("name") for uq in inspector.get_unique_constraints(TABLA)}
    indices = {ix["name"] for ix in inspector.get_indexes(TABLA)}

    with op.batch_alter_table(TABLA, naming_convention=NAMING_CONVENTION) as batch:
        if UNIQUE_NUEVA in existentes_uq:
            batch.drop_constraint(UNIQUE_NUEVA, type_="unique")
        if INDICE_MAC in indices:
            batch.drop_index(INDICE_MAC)
        batch.create_unique_constraint(UNIQUE_ANTIGUA, ["device_uid"])
        if "medidor_id" in columnas:
            batch.drop_column("medidor_id")
