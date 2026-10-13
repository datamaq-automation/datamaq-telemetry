"""crear_tabla_activos_unifilar

Revision ID: 9cef3dda7c50
Revises: c4e8a1d2f6b9
Create Date: 2026-10-11 12:52:27.583993

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9cef3dda7c50"
down_revision: str | Sequence[str] | None = "c4e8a1d2f6b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "activos_unifilar",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("planta_id", sa.String(64), nullable=False),
        sa.Column("nombre", sa.String(128), nullable=False),
        sa.Column(
            "tipo",
            sa.Enum(
                "TRANSFORMADOR",
                "TGBT",
                "TABLERO_SECCIONAL",
                "LINEA",
                "MAQUINA",
                "CARGA_VIRTUAL",
                name="tipo_activo_unifilar",
            ),
            nullable=False,
        ),
        sa.Column("parent_id", sa.String(64), nullable=True),
        sa.Column("device_id", sa.String(64), nullable=True),
        sa.Column("tension_nominal_v", sa.Float(), nullable=False),
        sa.Column("potencia_nominal_kw", sa.Float(), nullable=True),
        sa.Column("capacidad_nominal_kva", sa.Float(), nullable=True),
        sa.Column("categoria_uso", sa.String(64), nullable=True),
        sa.Column("uso_significativo", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("posicion_x", sa.Float(), nullable=True),
        sa.Column("posicion_y", sa.Float(), nullable=True),
        sa.Column("ancho", sa.Float(), nullable=True),
        sa.Column("alto", sa.Float(), nullable=True),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["planta_id"], ["facilities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="SET NULL"),
    )
    op.create_index("idx_activos_unifilar_planta", "activos_unifilar", ["planta_id"])
    op.create_index("idx_activos_unifilar_parent", "activos_unifilar", ["parent_id"])
    op.create_index("idx_activos_unifilar_device", "activos_unifilar", ["device_id"])


def downgrade() -> None:
    op.drop_index("idx_activos_unifilar_device", table_name="activos_unifilar")
    op.drop_index("idx_activos_unifilar_parent", table_name="activos_unifilar")
    op.drop_index("idx_activos_unifilar_planta", table_name="activos_unifilar")
    op.drop_table("activos_unifilar")
