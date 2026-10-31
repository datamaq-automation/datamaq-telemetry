"""src/infrastructure/sqlalchemy/models_parametros_regulatorios.py — Tarifas, facturas verificadas y parámetros regulatorios.

Datamaq#111 (fase 1): estos datos salen del código y viven en tablas versionadas, con distribuidora, tarifa,
vigencia y fuente (archivo y método). Comparten la `Base` de `models.py`; `alembic/env.py` importa este módulo
para que la metadata los vea. La carga inicial la hace la migración con los valores de
`src/adapters/gateways/parametros_regulatorios_iniciales.py`.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.sqlalchemy.models import Base


class TarifaCapacidadModel(Base):
    """Precio de capacidad verificado por distribuidora, tarifa y período."""

    __tablename__ = "tarifa_capacidad"
    # Una corrección es una fila nueva con otra vigencia_desde; el adaptador toma la vigente más reciente.
    __table_args__ = (
        UniqueConstraint("distribuidora", "tarifa", "periodo", "vigencia_desde", name="uq_tarifa_capacidad_vigencia"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    distribuidora: Mapped[str] = mapped_column(String(64), nullable=False)
    tarifa: Mapped[str] = mapped_column(String(32), nullable=False)
    periodo: Mapped[str] = mapped_column(String(7), nullable=False)
    fuente_archivo: Mapped[str] = mapped_column(String(255), nullable=False)
    fuente_metodo: Mapped[str] = mapped_column(String(500), nullable=False)
    vigencia_desde: Mapped[date] = mapped_column(Date, nullable=False)
    vigencia_hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    importe_capacidad_convenida_ars: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    csc_kw: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)


class FacturaVerificadaModel(Base):
    """Período con factura verificada contra el PDF: demanda adquirida o tg phi por bloque."""

    __tablename__ = "factura_verificada"
    # Una corrección de la misma factura es otra fila (otro fuente_archivo); el adaptador toma la más reciente.
    __table_args__ = (UniqueConstraint("planta_id", "periodo", "fuente_archivo", name="uq_factura_verificada_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    planta_id: Mapped[str] = mapped_column(String(64), nullable=False)
    distribuidora: Mapped[str] = mapped_column(String(64), nullable=False)
    tarifa: Mapped[str] = mapped_column(String(32), nullable=False)
    periodo: Mapped[str] = mapped_column(String(7), nullable=False)
    fuente_archivo: Mapped[str] = mapped_column(String(255), nullable=False)
    fuente_metodo: Mapped[str] = mapped_column(String(500), nullable=False)
    adquirida_kw: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    tg_fi_bloque_punta: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    tg_fi_bloque_valle: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    tg_fi_bloque_resto: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)


class ParametroRegulatorioModel(Base):
    """Parámetro regulatorio con clave, valor, alcance opcional (distribuidora y tarifa) y vigencia."""

    __tablename__ = "parametro_regulatorio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clave: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    valor: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    distribuidora: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tarifa: Mapped[str | None] = mapped_column(String(32), nullable=True)
    vigencia_desde: Mapped[date | None] = mapped_column(Date, nullable=True)
    vigencia_hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    fuente_archivo: Mapped[str] = mapped_column(String(255), nullable=False)
    fuente_metodo: Mapped[str] = mapped_column(String(500), nullable=False)
