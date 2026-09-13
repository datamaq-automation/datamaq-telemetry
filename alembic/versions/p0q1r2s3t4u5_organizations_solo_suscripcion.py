"""organizations pasa a ser la suscripción: se van name, tax_id y contacto (E2)

La identidad de la organización (nombre, CUIT, contacto) vive en
`data/organizaciones.yml`; acá queda el `id` como ancla de FK y el estado
comercial (`plan_id`, `pro_expires_at`, `free_tier_mode`), que tiene fecha de
vencimiento y no se gestiona por commit.

Backfill explícito: hasta ahora `free_tier_mode` se leía del YAML, no de esta
tabla, así que el valor en la base puede no coincidir. Se fija para las tres
organizaciones conocidas con lo que declaraba el YAML el 2026-09-13, creando la
fila si no existe. Idempotente.

Revision ID: p0q1r2s3t4u5
Revises: o9p0q1r2s3t4
Create Date: 2026-09-13 21:00:00.000000
"""

from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "p0q1r2s3t4u5"
down_revision: str | Sequence[str] | None = "o9p0q1r2s3t4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLA = "organizations"
COLUMNAS_IDENTIDAD = ("name", "tax_id", "contact_email", "contact_phone")

# Valores que declaraba data/organizaciones.yml el 2026-09-13 (fuente: el propio YAML).
FREE_TIER_POR_ORGANIZACION = {
    "09c09578-a860-4c61-8e97-2a13240adb8f": "VITRINA_ANONIMA",  # Hogar (medidor doméstico)
    "cf82b4be-0798-4beb-8978-2a27612d5761": "PRIVADO_BASICO",  # Vajillas Durax S.A. (Cristal Avellaneda)
    "edebb9a0-85e5-4bde-a370-e64bd9b9608c": "PRIVADO_BASICO",  # Cooperativa Unión Papelera Platense
}


def _columnas(inspector: sa.Inspector) -> set[str]:
    return {c["name"] for c in inspector.get_columns(TABLA)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLA):
        return

    # 1. Backfill del free tier antes de tocar columnas (usa la fila completa si existe).
    for org_id, modo in FREE_TIER_POR_ORGANIZACION.items():
        existe = bind.execute(sa.text(f"SELECT 1 FROM {TABLA} WHERE id = :id"), {"id": org_id}).first()
        if existe:
            bind.execute(
                sa.text(f"UPDATE {TABLA} SET free_tier_mode = :modo WHERE id = :id"), {"modo": modo, "id": org_id}
            )
        else:
            columnas = ["id", "free_tier_mode", "created_at", "updated_at"]
            valores = {"id": org_id, "modo": modo, "ahora": datetime.now(timezone.utc)}
            if "name" in _columnas(inspector):
                columnas.insert(1, "name")
                valores["name"] = org_id
            marcadores = ", ".join(
                {"free_tier_mode": ":modo", "created_at": ":ahora", "updated_at": ":ahora"}.get(c, f":{c}")
                for c in columnas
            )
            bind.execute(sa.text(f"INSERT INTO {TABLA} ({', '.join(columnas)}) VALUES ({marcadores})"), valores)

    # 2. Las columnas de identidad duplicaban el YAML.
    presentes = _columnas(inspector)
    with op.batch_alter_table(TABLA) as batch:
        for col in COLUMNAS_IDENTIDAD:
            if col in presentes:
                batch.drop_column(col)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(TABLA):
        return
    presentes = _columnas(inspector)
    with op.batch_alter_table(TABLA) as batch:
        if "name" not in presentes:
            batch.add_column(sa.Column("name", sa.String(150), nullable=False, server_default=""))
        if "tax_id" not in presentes:
            batch.add_column(sa.Column("tax_id", sa.String(50), nullable=True))
        if "contact_email" not in presentes:
            batch.add_column(sa.Column("contact_email", sa.String(120), nullable=True))
        if "contact_phone" not in presentes:
            batch.add_column(sa.Column("contact_phone", sa.String(50), nullable=True))
