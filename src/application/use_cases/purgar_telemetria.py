"""src/application/use_cases/purgar_telemetria.py."""

import time
from datetime import datetime, timedelta, timezone

from src.application.dtos.purga_dto import PurgaRequestDTO, PurgaResultadoDTO
from src.domain.telemetria.exceptions import CortePurgaFuturoError
from src.domain.telemetria.ports import (
    LoggerPort,
    RepositorioTelemetriaPort,
)
from src.domain.telemetria.services import PoliticaRetencionService


class PurgarTelemetriaExpiradaUseCase:
    def __init__(
        self,
        repo_telemetria: RepositorioTelemetriaPort,
        logger: LoggerPort | None = None,
    ):
        self.repo_telemetria = repo_telemetria
        self.logger = logger

    def ejecutar(self, dto: PurgaRequestDTO) -> PurgaResultadoDTO:
        inicio = time.time()
        ahora = datetime.now(timezone.utc)

        # 1. Fechas de corte según política
        if dto.corte_hasta is not None:
            if dto.corte_hasta > ahora:
                raise CortePurgaFuturoError(f"corte_hasta ({dto.corte_hasta.isoformat()}) es posterior a ahora")
            corte_instantaneas = dto.corte_hasta
            corte_energia = dto.corte_hasta
            corte_logs = dto.corte_hasta
            corte_alertas = dto.corte_hasta
        elif dto.dias_retencion_override is not None:
            corte_instantaneas = ahora - timedelta(days=dto.dias_retencion_override)
            corte_energia = ahora - timedelta(days=dto.dias_retencion_override)
            corte_logs = ahora - timedelta(days=dto.dias_retencion_override)
            corte_alertas = ahora - timedelta(days=dto.dias_retencion_override)
        else:
            # Por defecto: 45 días para instantáneas crudas (ISO 27001 A.8.10),
            # 5 años (1825 días) para agregados energéticos (ISO 50001),
            # 7 días para status logs y 30 días para alertas resueltas.
            dias_inst = dto.dias_retencion_instantaneas if dto.dias_retencion_instantaneas is not None else 45
            dias_ene = dto.dias_retencion_energia if dto.dias_retencion_energia is not None else (5 * 365)
            corte_instantaneas = ahora - timedelta(days=dias_inst)
            corte_energia = ahora - timedelta(days=dias_ene)
            corte_logs = PoliticaRetencionService.fecha_corte_status_logs(ahora, dias=7)
            corte_alertas = PoliticaRetencionService.fecha_corte_alertas_resueltas(ahora, dias=30)

        batch_size = dto.batch_size

        # 2. Drenado por lotes de instantaneas
        total_inst = 0
        while True:
            borrados = self.repo_telemetria.purgar_instantaneas_anteriores_a(corte_instantaneas, batch_size=batch_size)
            total_inst += borrados
            if borrados < batch_size:
                break

        # 3. Drenado por lotes de energias
        total_energia = 0
        while True:
            borrados = self.repo_telemetria.purgar_energias_anteriores_a(corte_energia, batch_size=batch_size)
            total_energia += borrados
            if borrados < batch_size:
                break

        # 4. Drenado por lotes de status logs
        total_logs = 0
        while True:
            borrados = self.repo_telemetria.purgar_status_logs_anteriores_a(corte_logs, batch_size=batch_size)
            total_logs += borrados
            if borrados < batch_size:
                break

        # 5. Drenado por lotes de alertas resueltas
        total_alertas = 0
        while True:
            borrados = self.repo_telemetria.purgar_alertas_resueltas_anteriores_a(corte_alertas, batch_size=batch_size)
            total_alertas += borrados
            if borrados < batch_size:
                break

        duracion = round(time.time() - inicio, 3)
        total_eliminados = total_inst + total_energia + total_logs + total_alertas

        if self.logger:
            self.logger.info(
                "purga_telemetria_completada",
                total_eliminados=total_eliminados,
                instantaneas=total_inst,
                energias=total_energia,
                status_logs=total_logs,
                alertas_resueltas=total_alertas,
                duracion_segundos=duracion,
            )

        return PurgaResultadoDTO(
            instantaneas_eliminadas=total_inst,
            energias_eliminadas=total_energia,
            status_logs_eliminados=total_logs,
            alertas_resueltas_eliminadas=total_alertas,
            total_registros_eliminados=total_eliminados,
            duracion_segundos=duracion,
            ejecutado_en=ahora,
        )
