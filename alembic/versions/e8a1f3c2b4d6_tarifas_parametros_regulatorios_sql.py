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

# Datos de la carga inicial, congelados en esta migración (datamaq#111). NO importar de src/: una migración
# aplicada no puede cambiar si cambia un módulo. Los valores son los literales de #111 (ver revisión de la decisión).
_TARIFAS_CAPACIDAD = [
    {
        "distribuidora": "Edesur",
        "tarifa": "T3 MT",
        "periodo": "2025-07",
        "fuente_archivo": "Cristal Avellaneda - EDESUR/2025-07.pdf",
        "vigencia_desde": "2025-07-01",
        "importe_capacidad_convenida_ars": "3521212.94",
        "csc_kw": "848.40",
        "fuente_metodo": "Factura Edesur 2025-07 (LSP A 9904-02469153 17), renglón 'Cap.Sum.Conv T3'. "
        "Carga inicial de #111 (literal previo en tarifas_distribuidora.py).",
    }
]

_FACTURAS_VERIFICADAS = [
    {
        "planta_id": "c64fd625-0037-4caa-b68a-800e8e0ee548",
        "distribuidora": "Edesur",
        "tarifa": "T3 MT",
        "periodo": "2025-07",
        "fuente_archivo": "Cristal Avellaneda - EDESUR/2025-07.pdf",
        "adquirida_kw": "930.00",
        "tg_fi_bloque_punta": None,
        "tg_fi_bloque_valle": None,
        "tg_fi_bloque_resto": None,
        "fuente_metodo": "Durax / Cristal Avellaneda, demanda adquirida de la factura verificada contra "
        "el PDF. Carga inicial de #111 (literal previo en penalizacion_periodo.py).",
    },
    {
        "planta_id": "4f68f653-a604-4834-8154-31f938248572",
        "distribuidora": "EDELAP",
        "tarifa": "T5M12",
        "periodo": "2024-08",
        "fuente_archivo": "Papelera platense - EDELAP/2024-08.pdf",
        "adquirida_kw": None,
        "tg_fi_bloque_punta": "0.431",
        "tg_fi_bloque_valle": "0.438",
        "tg_fi_bloque_resto": "0.426",
        "fuente_metodo": "UPP / Papelera platense, tg phi de la factura y Tg. Fi. punta/valle/resto "
        "verificados contra el PDF. Carga inicial de #111 (literal previo).",
    },
    {
        "planta_id": "4f68f653-a604-4834-8154-31f938248572",
        "distribuidora": "EDELAP",
        "tarifa": "T5M12",
        "periodo": "2023-12",
        "fuente_archivo": "Papelera platense - EDELAP/2023-12.pdf",
        "adquirida_kw": None,
        "tg_fi_bloque_punta": "0.483",
        "tg_fi_bloque_valle": "0.492",
        "tg_fi_bloque_resto": "0.481",
        "fuente_metodo": "UPP / Papelera platense, tg phi de la factura y Tg. Fi. punta/valle/resto "
        "verificados contra el PDF. Carga inicial de #111 (literal previo).",
    },
]

_PARAMETROS_REGULATORIOS = [
    {
        "clave": "factor_recargo_exceso",
        "valor": "1.5",
        "distribuidora": "Edesur",
        "tarifa": "T3 MT",
        "vigencia_desde": None,
        "fuente_archivo": "Cristal Avellaneda - EDESUR/2025-07.pdf",
        "fuente_metodo": "transcripcion_verificada",
    },
    {
        "clave": "limite_tg_fi_regimen_1992",
        "valor": "0.62",
        "distribuidora": "EDELAP",
        "tarifa": "T5M12",
        "vigencia_desde": None,
        "fuente_archivo": "decisions/2026-10-14_regimen-reactiva-edelap.md",
        "fuente_metodo": "Decisión registrada: contrato nacional de 1992 "
        "(decisions/2026-10-14_regimen-reactiva-edelap.md)",
    },
]

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
            for f in _TARIFAS_CAPACIDAD
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
            for f in _FACTURAS_VERIFICADAS
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
            for p in _PARAMETROS_REGULATORIOS
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_parametro_regulatorio_clave", table_name="parametro_regulatorio")
    op.drop_table("parametro_regulatorio")
    op.drop_table("factura_verificada")
    op.drop_table("tarifa_capacidad")
