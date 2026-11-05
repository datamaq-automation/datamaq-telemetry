"""src/infrastructure/sqlalchemy/repositories/telemetria_conteos_purga.py.

Conteos SQL de la simulación de purga (datamaq#119). Va en un mixin para que el repositorio
principal, que tiene límite de tamaño, no crezca.
"""

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.infrastructure.sqlalchemy.models import (
    DeviceAlertModel,
    DeviceStatusLogModel,
    TelemetryEnergyModel,
    TelemetryInstantaneousModel,
)


class ConteosPurgaSqlMixin:
    """Cuenta registros que la purga borraría. Requiere `self.db` (sesión SQLAlchemy)."""

    db: Session

    def contar_instantaneas_anteriores_a(self, fecha_limite: datetime) -> int:
        return int(
            self.db.query(func.count(TelemetryInstantaneousModel.id))
            .filter(TelemetryInstantaneousModel.recorded_at < fecha_limite)
            .scalar()
            or 0
        )

    def contar_energias_anteriores_a(self, fecha_limite: datetime) -> int:
        return int(
            self.db.query(func.count(TelemetryEnergyModel.id))
            .filter(TelemetryEnergyModel.recorded_at < fecha_limite)
            .scalar()
            or 0
        )

    def contar_status_logs_anteriores_a(self, fecha_limite: datetime) -> int:
        return int(
            self.db.query(func.count(DeviceStatusLogModel.id))
            .filter(DeviceStatusLogModel.recorded_at < fecha_limite)
            .scalar()
            or 0
        )

    def contar_alertas_resueltas_anteriores_a(self, fecha_limite: datetime) -> int:
        return int(
            self.db.query(func.count(DeviceAlertModel.id))
            .filter(DeviceAlertModel.is_resolved.is_(True), DeviceAlertModel.resolved_at < fecha_limite)
            .scalar()
            or 0
        )
