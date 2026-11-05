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
from src.domain.telemetria.servicios.politicas_suscripcion import (
    PISO_ALERTAS_DIAS,
    PISO_ENERGIA_DIAS,
    PISO_INSTANTANEAS_DIAS,
    PISO_LOGS_DIAS,
    PoliticaRetencionService,
)


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


TOLERANCIA_PISO = timedelta(minutes=1)


def calcular_cortes(dto: PurgaRequestDTO, ahora: datetime) -> dict[str, datetime]:
    """Cortes efectivos por tabla. Precedencia: corte_hasta > dias_retencion_override > explícitos y defaults.
    La validación de cotas y el borrado usan esta misma función, para que no puedan divergir."""
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
    # Defaults de la política (ISO 27001 A.8.10, ISO 50001, 7 y 30 días): mismas constantes que el piso.
    dias_inst = (
        dto.dias_retencion_instantaneas if dto.dias_retencion_instantaneas is not None else PISO_INSTANTANEAS_DIAS
    )
    dias_ene = dto.dias_retencion_energia if dto.dias_retencion_energia is not None else PISO_ENERGIA_DIAS
    return {
        "instantaneas": ahora - timedelta(days=dias_inst),
        "energia": ahora - timedelta(days=dias_ene),
        "logs": PoliticaRetencionService.fecha_corte_status_logs(ahora),
        "alertas": PoliticaRetencionService.fecha_corte_alertas_resueltas(ahora),
    }


def validar_cotas_purga(dto: PurgaSolicitudDTO, ahora: datetime) -> None:
    """Cotas de la ruta HTTP sobre los cortes EFECTIVOS. Cero o negativos: PurgaInvalidaError.
    Una tabla cuyo corte efectivo queda más reciente que su piso exige confirmar_retencion_menor."""
    _rechazar_no_positivos(dto)
    if dto.corte_hasta is not None and dto.corte_hasta > ahora:
        raise PurgaInvalidaError("corte_hasta no puede ser posterior a ahora.")
    if dto.confirmar_retencion_menor:
        return
    cortes = calcular_cortes(dto, ahora)
    bajo_piso: list[str] = []
    for tabla, clave, piso in (
        ("instantáneas", "instantaneas", PISO_INSTANTANEAS_DIAS),
        ("energía", "energia", PISO_ENERGIA_DIAS),
        ("status logs", "logs", PISO_LOGS_DIAS),
        ("alertas resueltas", "alertas", PISO_ALERTAS_DIAS),
    ):
        limite = ahora - timedelta(days=piso)
        if cortes[clave] > limite + TOLERANCIA_PISO:
            dias_efectivos = (ahora - cortes[clave]).days
            bajo_piso.append(f"{tabla} ({dias_efectivos} días efectivos < piso {piso})")
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
    total_registros: int | None,
    simulado: bool,
    accion: str | None = None,
) -> RegistrarAuditLogDTO:
    """Evento de auditoría de la purga: quién, con qué parámetros y cuántos registros."""
    parametros_serializables = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in parametros.items()}
    return RegistrarAuditLogDTO(
        categoria="SISTEMA",
        accion=accion or ("PURGA_SIMULADA" if simulado else "PURGA_EJECUTADA"),
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
        return calcular_cortes(dto, ahora)

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
