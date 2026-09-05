"""Modelos del contexto de desagregación de cargas (NILM).

Viven aparte de `models.py` para no empujar ese archivo contra el límite de 500 líneas
de `scripts/verify_code_size.py`. Comparten la misma `Base`, así que `alembic/env.py`
tiene que importar este módulo para que la metadata los vea.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.sqlalchemy.models import Base, ahora_utc, generate_uuid
from src.infrastructure.sqlalchemy.types import UtcDateTime


class LoadModel(Base):
    """Catálogo de cargas detrás de un medidor, con su firma eléctrica vigente.

    La firma va embebida en vez de en tabla aparte: cada carga tiene exactamente una
    firma vigente, y el historial de cómo se llegó a ella vive en
    `characterization_campaigns`.
    """

    __tablename__ = "loads"
    __table_args__ = (
        UniqueConstraint("device_id", "name", name="uq_loads_device_name"),
        Index("idx_loads_device", "device_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(30), default="OTROS", nullable=False)
    electrical_nature: Mapped[str] = mapped_column(String(20), default="MIXTA", nullable=False)
    operation_pattern: Mapped[str] = mapped_column(String(30), default="INDETERMINADO", nullable=False)
    nameplate_power_w: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    signature_power_w: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    signature_dispersion_w: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    signature_reactive_var: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    signature_power_factor: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    signature_on_seconds: Mapped[Decimal | None] = mapped_column(Numeric(10, 1), nullable=True)
    signature_on_mad_seconds: Mapped[Decimal | None] = mapped_column(Numeric(10, 1), nullable=True)
    signature_off_seconds: Mapped[Decimal | None] = mapped_column(Numeric(10, 1), nullable=True)
    signature_startup_peak_w: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    signature_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    signature_samples: Mapped[int | None] = mapped_column(nullable=True)
    signature_measured_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, onupdate=ahora_utc, nullable=False)


class CharacterizationCampaignModel(Base):
    """Ventana de medición a alta resolución sobre un medidor."""

    __tablename__ = "characterization_campaigns"
    __table_args__ = (Index("idx_campaigns_device_state", "device_id", "state"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    load_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("loads.id", ondelete="CASCADE"), nullable=True)
    campaign_type: Mapped[str] = mapped_column(String(20), nullable=False)
    state: Mapped[str] = mapped_column(String(20), default="EN_CURSO", nullable=False)
    start_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    planned_end_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    end_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    baseline_w: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    baseline_var: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    sample_count: Mapped[int] = mapped_column(default=0, nullable=False)
    discard_reason: Mapped[str | None] = mapped_column(String(30), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)


class CampaignSampleModel(Base):
    """Lectura de alta resolución capturada durante una campaña.

    Tabla propia y no `telemetry_instantaneous` por tres razones: no debe romper el
    supuesto de granularidad uniforme que asume la consulta de series, no debe caer en
    la purga por retención (es verdad de terreno, el activo del proyecto), y su vida
    útil está atada a la campaña que la produjo.
    """

    __tablename__ = "campaign_samples"
    __table_args__ = (
        # Idempotencia ante el redelivery de MQTT QoS 1, que la ventana de dedup de
        # 120 s del listener no cubre por sí sola.
        UniqueConstraint("campaign_id", "recorded_at", name="uq_campaign_samples_time"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("characterization_campaigns.id", ondelete="CASCADE"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    active_power_w: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    reactive_power_var: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    apparent_power_va: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    power_factor: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    voltage_v: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    current_a: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)


class LoadActivityIntervalModel(Base):
    """Un tramo en que se cree que una carga estuvo funcionando.

    `load_id` nulo es `NO_ATRIBUIDO`: se detectó actividad real que no se pudo imputar.
    Se guarda igual porque es lo que permite medir cuánto del consumo queda sin explicar.
    """

    __tablename__ = "load_activity_intervals"
    __table_args__ = (
        # Los límites del episodio son deterministas para los mismos datos, así que
        # re-correr el batch sobre una ventana actualiza en vez de duplicar.
        UniqueConstraint("device_id", "start_at", "end_at", name="uq_load_intervals_window"),
        Index("idx_load_intervals_load_time", "load_id", "start_at"),
        Index("idx_load_intervals_device_time", "device_id", "start_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    load_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("loads.id", ondelete="CASCADE"), nullable=True)
    start_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    end_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    avg_power_w: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    delta_reactive_var: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    energy_kwh: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    origin: Mapped[str] = mapped_column(String(20), default="REGLA", nullable=False)
    corrected_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    corrected_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)
