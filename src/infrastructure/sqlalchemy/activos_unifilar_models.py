"""Modelos ORM para la jerarquía de activos unifilar en MySQL (arquitectura híbrida)."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.sqlalchemy.models import Base, ahora_utc
from src.infrastructure.sqlalchemy.types import UtcDateTime

if TYPE_CHECKING:
    from src.infrastructure.sqlalchemy.models import DeviceModel, FacilityModel


class ActivoUnifilarModel(Base):
    """Nodo intermedio o activo del diagrama unifilar persistido en MySQL (arquitectura híbrida)."""

    __tablename__ = "activos_unifilar"
    __table_args__ = (
        Index("idx_activos_unifilar_planta", "planta_id"),
        Index("idx_activos_unifilar_parent", "parent_id"),
        Index("idx_activos_unifilar_device", "device_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    planta_id: Mapped[str] = mapped_column(String(64), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False)
    nombre: Mapped[str] = mapped_column(String(128), nullable=False)
    tipo: Mapped[str] = mapped_column(
        Enum(
            "TRANSFORMADOR",
            "TGBT",
            "TABLERO_SECCIONAL",
            "LINEA",
            "MAQUINA",
            "CARGA_VIRTUAL",
            name="tipo_activo_unifilar",
        ),
        nullable=False,
    )
    parent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("devices.id", ondelete="SET NULL"), nullable=True
    )
    tension_nominal_v: Mapped[float] = mapped_column(Float, nullable=False)
    potencia_nominal_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    capacidad_nominal_kva: Mapped[float | None] = mapped_column(Float, nullable=True)
    categoria_uso: Mapped[str | None] = mapped_column(String(64), nullable=True)
    uso_significativo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    posicion_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    posicion_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    ancho: Mapped[float | None] = mapped_column(Float, nullable=True)
    alto: Mapped[float | None] = mapped_column(Float, nullable=True)
    orden: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    creado_en: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, onupdate=ahora_utc, nullable=False)

    planta: Mapped["FacilityModel"] = relationship()
    device: Mapped[Optional["DeviceModel"]] = relationship()
