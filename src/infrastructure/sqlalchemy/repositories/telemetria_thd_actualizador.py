"""src/infrastructure/sqlalchemy/repositories/telemetria_thd_actualizador.py — THD sobre la última instantánea.

Separado de MySQLTelemetriaRepository para respetar el límite de tamaño de esa clase.
"""

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import desc
from sqlalchemy.orm import Session

from src.domain.telemetria.servicios.harmonics_thd import ThdFase
from src.infrastructure.sqlalchemy.models import TelemetryInstantaneousModel


def actualizar_thd_en_ultima_instantanea(
    db: Session,
    dispositivo_id: str,
    momento: datetime,
    ventana_s: int,
    thd: dict[str, ThdFase],
) -> bool:
    """Completa THDv y THDi por fase en la última fila persistida del dispositivo dentro de
    (momento - ventana_s, momento]. Fase sin valor no pisa las demás. Devuelve False si no hay fila."""
    fila = (
        db.query(TelemetryInstantaneousModel)
        .filter(
            TelemetryInstantaneousModel.device_id == dispositivo_id,
            TelemetryInstantaneousModel.recorded_at <= momento,
            TelemetryInstantaneousModel.recorded_at > momento - timedelta(seconds=ventana_s),
        )
        .order_by(desc(TelemetryInstantaneousModel.recorded_at))
        .first()
    )
    if fila is None:
        return False
    for fase, sufijo in (("R", "r"), ("S", "s"), ("T", "t")):
        valores = thd.get(fase)
        if valores is None:
            continue
        if valores.thd_v_pct is not None:
            setattr(fila, f"thd_v_{sufijo}", Decimal(str(valores.thd_v_pct)))
        if valores.thd_i_pct is not None:
            setattr(fila, f"thd_i_{sufijo}", Decimal(str(valores.thd_i_pct)))
    db.commit()
    return True
