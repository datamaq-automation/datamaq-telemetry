"""scripts/job_diagnostico_semanal.py — Job semanal: diagnóstico TI + alertas."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.application.services.diagnostico_ti_app_service import (
    EjecutarDiagnosticoTIApplicationService,
)
from src.domain.telemetria.ports import (
    RepositorioDispositivosPort,
    RepositorioTelemetriaPort,
)
from src.domain.telemetria.servicios.analizador_calidad_metrologica import (
    AnalizadorMetrologicoService,
)


class JobDiagnosticoSemanal:
    """Diagnóstico semanal de configuración TI."""

    def __init__(
        self,
        app_service: EjecutarDiagnosticoTIApplicationService,
        repo_dispositivos: RepositorioDispositivosPort,
        repo_telemetria: RepositorioTelemetriaPort,
    ):
        self.app_service = app_service
        self.repo_dispositivos = repo_dispositivos
        self.repo_telemetria = repo_telemetria

    def ejecutar(self) -> dict:
        """Ejecuta diagnóstico para dispositivos con anomalías recientes."""
        resultado = {"dispositivos_procesados": 0, "alertas_enviadas": 0, "errores": []}
        ahora = datetime.now(timezone.utc)
        hace_7d = ahora - timedelta(days=7)

        try:
            dispositivos_con_anomalias = self._obtener_dispositivos_con_anomalias(hace_7d, ahora)
            for device_id in dispositivos_con_anomalias:
                try:
                    dispositivo = self.repo_dispositivos.obtener_por_id(device_id)
                    if not dispositivo:
                        resultado["errores"].append(f"Dispositivo {device_id} no encontrado")
                        continue

                    resultado["dispositivos_procesados"] += 1
                    fases_set = AnalizadorMetrologicoService.fases_con_ti_como_lista(dispositivo.fases_con_ti)
                    fases_con_ti = tuple(sorted(fases_set))
                    diagnostico = self.app_service.ejecutar(device_id, fases_con_ti, periodo_horas=48)

                    if diagnostico.candidatos and diagnostico.candidatos[0].score > 0.95:
                        resultado["alertas_enviadas"] += 1

                except Exception as e:
                    resultado["errores"].append(f"Error en {device_id}: {e!s}")

        except Exception as e:
            resultado["errores"].append(f"Error general: {e!s}")

        return resultado

    def _obtener_dispositivos_con_anomalias(self, desde: datetime, hasta: datetime) -> list[str]:
        """Obtiene lista única de device_id con anomalías en rango."""
        from sqlalchemy import text

        from src.infrastructure.sqlalchemy.repositories.telemetria_repository import (
            MySQLTelemetriaRepository,
        )

        if not isinstance(self.repo_telemetria, MySQLTelemetriaRepository):
            return []

        query = text(
            "SELECT DISTINCT device_id FROM telemetria_anomalias WHERE recorded_at >= :desde AND recorded_at <= :hasta"
        )
        result = self.repo_telemetria.db.execute(query, {"desde": desde, "hasta": hasta})
        return [row[0] for row in result.all()]
