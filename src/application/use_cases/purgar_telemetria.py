"""src/application/use_cases/purgar_telemetria.py.

El camino de `ejecutar` lo usan scripts/purge_telemetry.py y el timer datamaq-purge: no cambia.
Las cotas de piso y la simulación por defecto (datamaq#119) viven en la ruta HTTP, a través de
`validar_cotas_purga` y `simular`; el caso de uso solo rechaza cero y negativos.
"""

import time
from datetime import datetime, timedelta, timezone
from typing import Any

from src.application.dtos.audit_dto import RegistrarAuditLogDTO
from src.application.dtos.purga_dto import PurgaRequestDTO, PurgaResultadoDTO, PurgaSolicitudDTO
from src.domain.telemetria.exceptions import CortePurgaFuturoError, DominioTelemetriaException
from src.domain.telemetria.ports import LoggerPort, RepositorioTelemetriaPort
from src.domain.telemetria.services import PoliticaRetencionService

# Piso de retención por tabla (datamaq#119). La ruta HTTP exige confirmación explícita para
# recortar por debajo de estos valores.
PISO_INSTANTANEAS_DIAS = 45
PISO_ENERGIA_DIAS = 5 * 365  # 1825: línea base ISO 50001
PISO_LOGS_DIAS = 7
PISO_ALERTAS_DIAS = 30


class PurgaInvalidaError(DominioTelemetriaException):
    """Parámetro de purga cero o negativo. Ninguna confirmación lo habilita."""


class CotasPurgaError(DominioTelemetriaException):
    """La purga recortaría una tabla por debajo de su piso sin confirmación explícita."""


def _rechazar_no_positivos(dto: PurgaRequestDTO) -> None:
    for nombre, valor in (
        ("dias_retencion_override", dto.dias_retencion_override),
        ("dias_retencion_instantaneas", dto.dias_retencion_instantaneas),
        ("dias_retencion_energia", dto.dias_retencion_energia),
    ):
        if valor is not None and valor <= 0:
            raise PurgaInvalidaError(f"{nombre} debe ser mayor que 0 (recibido {valor}).")


def validar_cotas_purga(dto: PurgaSolicitudDTO, ahora: datetime) -> None:
    """Cotas de la ruta HTTP. Cero o negativos: PurgaInvalidaError. Bajo el piso sin
    `confirmar_retencion_menor`: CotasPurgaError."""
    _rechazar_no_positivos(dto)
    if dto.corte_hasta is not None and dto.corte_hasta > ahora:
        raise PurgaInvalidaError("corte_hasta no puede ser posterior a ahora.")
    if dto.confirmar_retencion_menor:
        return

    bajo_piso: list[str] = []
    override = dto.dias_retencion_override
    for tabla, explicito, piso in (
        ("instantáneas", dto.dias_retencion_instantaneas, PISO_INSTANTANEAS_DIAS),
        ("energía", dto.dias_retencion_energia, PISO_ENERGIA_DIAS),
        ("status logs", None, PISO_LOGS_DIAS),
        ("alertas resueltas", None, PISO_ALERTAS_DIAS),
    ):
        dias = explicito if explicito is not None else override
        if dias is not None and dias < piso:
            bajo_piso.append(f"{tabla} ({dias} días < piso {piso})")
    if dto.corte_hasta is not None and dto.corte_hasta > ahora - timedelta(days=PISO_ENERGIA_DIAS):
        bajo_piso.append(f"corte_hasta ({dto.corte_hasta.isoformat()}) más reciente que el piso de energía")
    if bajo_piso:
        raise CotasPurgaError(
            "La purga recorta por debajo del piso de retención sin confirmación explícita: "
            + "; ".join(bajo_piso)
            + ". Enviar confirmar_retencion_menor=true para continuar."
        )


def construir_auditoria_purga(
    actor_usuario_id: str | None,
    actor_email: str | None,
    actor_ip: str | None,
    parametros: dict[str, Any],
    total_registros: int,
    simulado: bool,
) -> RegistrarAuditLogDTO:
    """Evento de auditoría de la purga: quién, con qué parámetros y cuántos registros."""
    parametros_serializables = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in parametros.items()}
    return RegistrarAuditLogDTO(
        categoria="SISTEMA",
        accion="PURGA_SIMULADA" if simulado else "PURGA_EJECUTADA",
        resultado="EXITO",
        actor_usuario_id=actor_usuario_id,
        actor_email=actor_email,
        actor_ip=actor_ip,
        recurso_tipo="telemetria",
        metadatos={"total_registros": total_registros, "parametros": parametros_serializables},
    )


class PurgarTelemetriaExpiradaUseCase:
    def __init__(
        self,
        repo_telemetria: RepositorioTelemetriaPort,
        logger: LoggerPort | None = None,
    ) -> None:
        self.repo_telemetria = repo_telemetria
        self.logger = logger

    def _calcular_cortes(self, dto: PurgaRequestDTO, ahora: datetime) -> dict[str, datetime]:
        """Fechas de corte por tabla según la política (corte_hasta, override o defaults)."""
        if dto.corte_hasta is not None:
            if dto.corte_hasta > ahora:
                raise CortePurgaFuturoError(f"corte_hasta ({dto.corte_hasta.isoformat()}) es posterior a ahora")
            return {
                "instantaneas": dto.corte_hasta,
                "energia": dto.corte_hasta,
                "logs": dto.corte_hasta,
                "alertas": dto.corte_hasta,
            }
        if dto.dias_retencion_override is not None:
            corte = ahora - timedelta(days=dto.dias_retencion_override)
            return {"instantaneas": corte, "energia": corte, "logs": corte, "alertas": corte}
        # Por defecto: 45 días para instantáneas crudas (ISO 27001 A.8.10),
        # 5 años (1825 días) para agregados energéticos (ISO 50001),
        # 7 días para status logs y 30 días para alertas resueltas.
        dias_inst = dto.dias_retencion_instantaneas if dto.dias_retencion_instantaneas is not None else 45
        dias_ene = dto.dias_retencion_energia if dto.dias_retencion_energia is not None else (5 * 365)
        return {
            "instantaneas": ahora - timedelta(days=dias_inst),
            "energia": ahora - timedelta(days=dias_ene),
            "logs": PoliticaRetencionService.fecha_corte_status_logs(ahora, dias=7),
            "alertas": PoliticaRetencionService.fecha_corte_alertas_resueltas(ahora, dias=30),
        }

    def simular(self, dto: PurgaRequestDTO) -> PurgaResultadoDTO:
        """Cuenta los registros que borraría `ejecutar` con los mismos parámetros. No borra nada."""
        _rechazar_no_positivos(dto)
        ahora = datetime.now(timezone.utc)
        cortes = self._calcular_cortes(dto, ahora)
        inst = self.repo_telemetria.contar_instantaneas_anteriores_a(cortes["instantaneas"])
        ene = self.repo_telemetria.contar_energias_anteriores_a(cortes["energia"])
        logs = self.repo_telemetria.contar_status_logs_anteriores_a(cortes["logs"])
        alertas = self.repo_telemetria.contar_alertas_resueltas_anteriores_a(cortes["alertas"])
        return PurgaResultadoDTO(
            instantaneas_eliminadas=inst,
            energias_eliminadas=ene,
            status_logs_eliminados=logs,
            alertas_resueltas_eliminadas=alertas,
            total_registros_eliminados=inst + ene + logs + alertas,
            duracion_segundos=0.0,
            ejecutado_en=ahora,
            simulado=True,
        )

    def ejecutar(self, dto: PurgaRequestDTO) -> PurgaResultadoDTO:
        inicio = time.time()
        _rechazar_no_positivos(dto)
        ahora = datetime.now(timezone.utc)
        cortes = self._calcular_cortes(dto, ahora)

        batch_size = dto.batch_size

        # 2. Drenado por lotes de instantaneas
        total_inst = 0
        while True:
            borrados = self.repo_telemetria.purgar_instantaneas_anteriores_a(
                cortes["instantaneas"], batch_size=batch_size
            )
            total_inst += borrados
            if borrados < batch_size:
                break

        # 3. Drenado por lotes de energias
        total_energia = 0
        while True:
            borrados = self.repo_telemetria.purgar_energias_anteriores_a(cortes["energia"], batch_size=batch_size)
            total_energia += borrados
            if borrados < batch_size:
                break

        # 4. Drenado por lotes de status logs
        total_logs = 0
        while True:
            borrados = self.repo_telemetria.purgar_status_logs_anteriores_a(cortes["logs"], batch_size=batch_size)
            total_logs += borrados
            if borrados < batch_size:
                break

        # 5. Drenado por lotes de alertas resueltas
        total_alertas = 0
        while True:
            borrados = self.repo_telemetria.purgar_alertas_resueltas_anteriores_a(
                cortes["alertas"], batch_size=batch_size
            )
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
