"""Adaptador que implementa RepositorioTelemetriaPort para diagnostico_ti_app_service."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from src.application.services.diagnostico_ti_app_service import RepositorioTelemetriaPort
from src.infrastructure.sqlalchemy.models import TelemetryInstantaneousModel


class TelemetriaDiagnosticoAdapter(RepositorioTelemetriaPort):
    """Adaptador: MySQLTelemetriaRepository → RepositorioTelemetriaPort."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def obtener_mediciones_dispositivo(
        self,
        dispositivo_id: str,
        inicio: datetime,
        fin: datetime,
    ) -> list[dict]:
        """Obtiene mediciones del dispositivo en el período especificado."""
        stmt = (
            select(TelemetryInstantaneousModel)
            .where(TelemetryInstantaneousModel.device_id == dispositivo_id)
            .where(TelemetryInstantaneousModel.recorded_at >= inicio)
            .where(TelemetryInstantaneousModel.recorded_at <= fin)
            .order_by(desc(TelemetryInstantaneousModel.recorded_at))
        )
        registros = self.db.execute(stmt).scalars().all()

        resultado = []
        for reg in registros:
            resultado.append(
                {
                    "registrado_en": reg.recorded_at,
                    "p_r": reg.active_power_r,
                    "p_s": reg.active_power_s,
                    "p_t": reg.active_power_t,
                    "q_r": reg.reactive_power_r,
                    "q_s": reg.reactive_power_s,
                    "q_t": reg.reactive_power_t,
                    "s_r": reg.apparent_power_r,
                    "s_s": reg.apparent_power_s,
                    "s_t": reg.apparent_power_t,
                    "fp_r": reg.power_factor_r,
                    "fp_s": reg.power_factor_s,
                    "fp_t": reg.power_factor_t,
                }
            )

        return resultado
