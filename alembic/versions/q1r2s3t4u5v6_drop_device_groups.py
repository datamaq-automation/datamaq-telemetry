"""drop device_groups y device_group_members: concepto duplicado del unifilar (E3)

"Sumar estos medidores" es lo que hace un nodo virtual del unifilar
(`ArbolUnifilarService.medidores_frontera`); un alimentador es un `seccional`
con hijos declarado en `data/organizaciones.yml`. Los dos casos de uso ya
compartían `agregacion_dispositivos.py`. No se migra: se borra.

Aborta si alguna de las dos tablas tiene filas — en producción están vacías
según la auditoría del frontend (2026-09-13), pero no se da por hecho: antes
que borrar datos cargados, que falle el deploy y haga rollback (D-5).

Revision ID: q1r2s3t4u5v6
Revises: p0q1r2s3t4u5
Create Date: 2026-09-13 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "q1r2s3t4u5v6"
down_revision: str | Sequence[str] | None = "p0q1r2s3t4u5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class TablaConDatosError(RuntimeError):
    pass


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for tabla in ("device_group_members", "device_groups"):  # miembros primero: FK a device_groups
        if not inspector.has_table(tabla):
            continue
        filas = bind.execute(sa.text(f"SELECT COUNT(*) FROM {tabla}")).scalar() or 0
        if filas:
            raise TablaConDatosError(
                f"{tabla} tiene {filas} filas; esta migración no borra datos cargados. "
                "Migrá esos grupos a nodos `seccional` del unifilar en el YAML y vaciá la tabla antes."
            )
        op.drop_table(tabla)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("device_groups"):
        op.create_table(
            "device_groups",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("facility_id", sa.String(36), sa.ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(150), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("idx_device_group_facility", "device_groups", ["facility_id"])
    if not inspector.has_table("device_group_members"):
        op.create_table(
            "device_group_members",
            sa.Column(
                "group_id", sa.String(36), sa.ForeignKey("device_groups.id", ondelete="CASCADE"), primary_key=True
            ),
            sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True),
        )
