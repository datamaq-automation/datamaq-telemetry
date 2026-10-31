"""tarifas, facturas verificadas y parámetros regulatorios en SQL (datamaq#111, fase 1)

Revision ID: e8a1f3c2b4d6
Revises: d5f2a9c1e7b3
Create Date: 2026-10-31 12:00:00.000000

Mueve a tablas versionadas los datos de negocio que vivían como literales en `src/domain/telemetria`:
el precio de capacidad (`tarifa_capacidad`), los períodos con factura verificada (`factura_verificada`)
y los parámetros regulatorios (`parametro_regulatorio`: factor de recargo por exceso y límite de tg phi del
régimen 1992). La carga inicial reproduce los valores de hoy sin cambiar ninguno; la fuente de cada fila va en
`fuente_archivo` y `fuente_metodo`.

Los 0,95 de FP NO se migran en esta fase: quedan en el código hasta que se decida el alcance por distribuidora.
Reversible: el downgrade borra las tres tablas. No corre contra ninguna base desde el repo: lo aplica el release
de telemetry, con respaldo previo (decisions/2026-10-29_bd-fuente-de-verdad-progresiva.md).
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

import sqlalchemy as sa

from alembic import op
from src.adapters.gateways.parametros_regulatorios_iniciales import (
    FACTURAS_VERIFICADAS_INICIALES,
    PARAMETROS_REGULATORIOS_INICIALES,
    TARIFAS_CAPACIDAD_INICIALES,
)

revision: str = "e8a1f3c2b4d6"
down_revision: str | Sequence[str] | None = "d5f2a9c1e7b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _fecha(valor: str | None) -> date | None:
    return date.fromisoformat(valor) if valor else None


def _decimal(valor: str | None) -> Decimal | None:
    return Decimal(valor) if valor is not None else None


def upgrade() -> None:
    op.create_table(
        "tarifa_capacidad",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("distribuidora", sa.String(length=64), nullable=False),
        sa.Column("tarifa", sa.String(length=32), nullable=False),
        sa.Column("periodo", sa.String(length=7), nullable=False),
        sa.Column("fuente_archivo", sa.String(length=255), nullable=False),
        sa.Column("fuente_metodo", sa.String(length=500), nullable=False),
        sa.Column("vigencia_desde", sa.Date(), nullable=False),
        sa.Column("vigencia_hasta", sa.Date(), nullable=True),
        sa.Column("importe_capacidad_convenida_ars", sa.Numeric(18, 2), nullable=False),
        sa.Column("csc_kw", sa.Numeric(12, 2), nullable=False),
        sa.UniqueConstraint(
            "distribuidora", "tarifa", "periodo", "vigencia_desde", name="uq_tarifa_capacidad_vigencia"
        ),
    )
    op.create_table(
        "factura_verificada",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("planta_id", sa.String(length=64), nullable=False),
        sa.Column("distribuidora", sa.String(length=64), nullable=False),
        sa.Column("tarifa", sa.String(length=32), nullable=False),
        sa.Column("periodo", sa.String(length=7), nullable=False),
        sa.Column("fuente_archivo", sa.String(length=255), nullable=False),
        sa.Column("fuente_metodo", sa.String(length=500), nullable=False),
        sa.Column("adquirida_kw", sa.Numeric(12, 2), nullable=True),
        sa.Column("tg_fi_bloque_punta", sa.Numeric(6, 3), nullable=True),
        sa.Column("tg_fi_bloque_valle", sa.Numeric(6, 3), nullable=True),
        sa.Column("tg_fi_bloque_resto", sa.Numeric(6, 3), nullable=True),
        sa.UniqueConstraint("planta_id", "periodo", "fuente_archivo", name="uq_factura_verificada_version"),
    )
    op.create_table(
        "parametro_regulatorio",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("clave", sa.String(length=64), nullable=False),
        sa.Column("valor", sa.Numeric(10, 4), nullable=False),
        sa.Column("distribuidora", sa.String(length=64), nullable=True),
        sa.Column("tarifa", sa.String(length=32), nullable=True),
        sa.Column("vigencia_desde", sa.Date(), nullable=True),
        sa.Column("vigencia_hasta", sa.Date(), nullable=True),
        sa.Column("fuente_archivo", sa.String(length=255), nullable=False),
        sa.Column("fuente_metodo", sa.String(length=500), nullable=False),
    )
    op.create_index("ix_parametro_regulatorio_clave", "parametro_regulatorio", ["clave"])

    tarifas = sa.table(
        "tarifa_capacidad",
        sa.column("distribuidora", sa.String),
        sa.column("tarifa", sa.String),
        sa.column("periodo", sa.String),
        sa.column("fuente_archivo", sa.String),
        sa.column("fuente_metodo", sa.String),
        sa.column("vigencia_desde", sa.Date),
        sa.column("vigencia_hasta", sa.Date),
        sa.column("importe_capacidad_convenida_ars", sa.Numeric(18, 2)),
        sa.column("csc_kw", sa.Numeric(12, 2)),
    )
    op.bulk_insert(
        tarifas,
        [
            {
                "distribuidora": f["distribuidora"],
                "tarifa": f["tarifa"],
                "periodo": f["periodo"],
                "fuente_archivo": f["fuente_archivo"],
                "fuente_metodo": f["fuente_metodo"],
                "vigencia_desde": _fecha(f["vigencia_desde"]),
                "vigencia_hasta": None,
                "importe_capacidad_convenida_ars": _decimal(f["importe_capacidad_convenida_ars"]),
                "csc_kw": _decimal(f["csc_kw"]),
            }
            for f in TARIFAS_CAPACIDAD_INICIALES
        ],
    )

    facturas = sa.table(
        "factura_verificada",
        sa.column("planta_id", sa.String),
        sa.column("distribuidora", sa.String),
        sa.column("tarifa", sa.String),
        sa.column("periodo", sa.String),
        sa.column("fuente_archivo", sa.String),
        sa.column("fuente_metodo", sa.String),
        sa.column("adquirida_kw", sa.Numeric(12, 2)),
        sa.column("tg_fi_bloque_punta", sa.Numeric(6, 3)),
        sa.column("tg_fi_bloque_valle", sa.Numeric(6, 3)),
        sa.column("tg_fi_bloque_resto", sa.Numeric(6, 3)),
    )
    op.bulk_insert(
        facturas,
        [
            {
                "planta_id": f["planta_id"],
                "distribuidora": f["distribuidora"],
                "tarifa": f["tarifa"],
                "periodo": f["periodo"],
                "fuente_archivo": f["fuente_archivo"],
                "fuente_metodo": f["fuente_metodo"],
                "adquirida_kw": _decimal(f["adquirida_kw"]),
                "tg_fi_bloque_punta": _decimal(f["tg_fi_bloque_punta"]),
                "tg_fi_bloque_valle": _decimal(f["tg_fi_bloque_valle"]),
                "tg_fi_bloque_resto": _decimal(f["tg_fi_bloque_resto"]),
            }
            for f in FACTURAS_VERIFICADAS_INICIALES
        ],
    )

    parametros = sa.table(
        "parametro_regulatorio",
        sa.column("clave", sa.String),
        sa.column("valor", sa.Numeric(10, 4)),
        sa.column("distribuidora", sa.String),
        sa.column("tarifa", sa.String),
        sa.column("vigencia_desde", sa.Date),
        sa.column("fuente_archivo", sa.String),
        sa.column("fuente_metodo", sa.String),
    )
    op.bulk_insert(
        parametros,
        [
            {
                "clave": p["clave"],
                "valor": _decimal(p["valor"]),
                "distribuidora": p["distribuidora"],
                "tarifa": p["tarifa"],
                "vigencia_desde": _fecha(p["vigencia_desde"]),
                "fuente_archivo": p["fuente_archivo"],
                "fuente_metodo": p["fuente_metodo"],
            }
            for p in PARAMETROS_REGULATORIOS_INICIALES
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_parametro_regulatorio_clave", table_name="parametro_regulatorio")
    op.drop_table("parametro_regulatorio")
    op.drop_table("factura_verificada")
    op.drop_table("tarifa_capacidad")
