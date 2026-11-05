"""src/infrastructure/sqlalchemy/models_consumo_mqtt.py — Agregado de mensajes y bytes MQTT por equipo y hora (#93).

Vive aparte de ``models.py`` por el límite de líneas de ``scripts/verify_code_size.py``. Comparte la
misma ``Base``, así que ``alembic/env.py`` lo importa para que la metadata lo vea.
"""

from datetime import datetime

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.sqlalchemy.models import Base
from src.infrastructure.sqlalchemy.types import UtcDateTime


class ConsumoMqttHorarioModel(Base):
    """Mensajes y bytes de payload que llegaron al servidor, por UID de topic y hora UTC."""

    __tablename__ = "mqtt_consumo_horario"

    uid: Mapped[str] = mapped_column(String(32), primary_key=True)
    hora: Mapped[datetime] = mapped_column(UtcDateTime(), primary_key=True)
    mensajes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    bytes_payload: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
