# src/application/use_cases/monitorear_salud_dispositivos.py
from datetime import datetime, timezone
from typing import ClassVar

from src.application.dtos.alerta_dto import AlertaResponseDTO
from src.application.mappers.alerta_mapper import AlertaMapper
from src.domain.telemetria.entities import AlertaDispositivo, Dispositivo
from src.domain.telemetria.ports import (
    LoggerPort,
    NotificadorAlertasPort,
    PublicadorEventosPort,
    RepositorioDispositivosPort,
    RepositorioTelemetriaPort,
)
from src.domain.telemetria.services import CooldownNotificacionesAlertasService
from src.domain.telemetria.value_objects import (
    EstadoDispositivo,
    ReglaAlertaConectividad,
    SeveridadAlerta,
)


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


class MonitorearSaludDispositivosUseCase:
    """Caso de uso de watchdog de backend que verifica periódicamente si los dispositivos

    han superado el tiempo límite de transmisión sin recibir telemetría (SLA de conectividad).
    """

    _cooldown_notificaciones: ClassVar[CooldownNotificacionesAlertasService] = CooldownNotificacionesAlertasService()
    _notificador: ClassVar[NotificadorAlertasPort | None] = None
    _destinatarios: ClassVar[list[str]] = []

    def __init__(
        self,
        repo_dispositivos: RepositorioDispositivosPort,
        repo_telemetria: RepositorioTelemetriaPort,
        publicador: PublicadorEventosPort | None = None,
        logger: LoggerPort | None = None,
        regla: ReglaAlertaConectividad | None = None,
        generar_alerta: bool = True,
    ) -> None:
        """`generar_alerta=False` solo marca OFFLINE, sin abrir la alerta PÉRDIDA_COMUNICACIÓN (#19: su texto y su
        activación los decide el dueño; en producción la controla DISPOSITIVO_OFFLINE_ALERTA_HABILITADA)."""
        self._repo_dispositivos = repo_dispositivos
        self._repo_telemetria = repo_telemetria
        self._publicador = publicador
        self._logger = logger
        self._regla = regla or ReglaAlertaConectividad()
        self._generar_alerta = generar_alerta

    @classmethod
    def configurar_notificador(
        cls,
        notificador: NotificadorAlertasPort | None,
        destinatarios: list[str] | None = None,
    ) -> None:
        cls._notificador = notificador
        cls._destinatarios = destinatarios or []

    def _evaluar_dispositivo(self, dev: Dispositivo, momento_actual: datetime) -> AlertaDispositivo | None:
        if not dev.esta_activo or dev.visto_por_ultima_vez is None:
            return None

        segundos_inactivo = (momento_actual - dev.visto_por_ultima_vez).total_seconds()
        if segundos_inactivo <= self._regla.timeout_segundos:
            return None

        if dev.estado == EstadoDispositivo.ONLINE:
            dev.marcar_offline()
            # Solo estado y última recepción: `guardar` reescribía el dispositivo entero con lo que trajo `listar`.
            self._repo_dispositivos.actualizar_heartbeat(dev.id, dev.estado, dev.visto_por_ultima_vez)
            if self._logger:
                self._logger.info(
                    "dispositivo_marcado_offline",
                    dispositivo_id=dev.id,
                    mac=dev.device_uid.valor,
                    segundos_inactivo=round(segundos_inactivo),
                )

        if not self._generar_alerta:
            return None

        alertas_abiertas = self._repo_telemetria.listar_alertas(
            dispositivo_id=dev.id, solo_abiertas=True, severidad=SeveridadAlerta.CRITICAL.value
        )
        if any(a.tipo_alerta == "PÉRDIDA_COMUNICACIÓN" or a.categoria == "CONECTIVIDAD" for a in alertas_abiertas):
            return None

        minutos = int(segundos_inactivo // 60)
        mensaje = (
            f"🚨 Corte de Comunicación: El medidor '{dev.nombre}' ({dev.device_uid.valor}) "
            f"ha dejado de transmitir datos hace más de {minutos} minutos. "
            f"Último dato recibido: {dev.visto_por_ultima_vez.strftime('%d/%m/%Y %H:%M hs')}."
        )

        alerta = AlertaDispositivo(
            id=None,
            dispositivo_id=dev.id,
            tipo_alerta="PÉRDIDA_COMUNICACIÓN",
            severidad=SeveridadAlerta.CRITICAL,
            mensaje=mensaje,
            esta_resuelta=False,
            disparada_en=momento_actual,
            valor_medido=segundos_inactivo,
            valor_umbral=float(self._regla.timeout_segundos),
            unidad="s",
            categoria="CONECTIVIDAD",
        )

        self._repo_telemetria.guardar_alerta(alerta)

        if self._publicador:
            self._publicador.publicar_telemetria_en_vivo(
                f"telemetria/alertas/{dev.device_uid.valor}",
                AlertaMapper.to_dto(alerta).model_dump(mode="json"),
            )

        if (
            self._notificador
            and self._destinatarios
            and self._cooldown_notificaciones.debe_notificar(alerta.dispositivo_id, alerta.tipo_alerta)
        ):
            self._notificador.notificar_alerta_critica(alerta, dev, self._destinatarios)
            self._cooldown_notificaciones.registrar_notificacion(alerta.dispositivo_id, alerta.tipo_alerta)

        if self._logger:
            self._logger.warning(
                "alerta_corte_comunicacion_generada",
                dispositivo_id=dev.id,
                mac=dev.device_uid.valor,
                segundos_inactivo=segundos_inactivo,
            )

        return alerta

    def ejecutar(self, ahora: datetime | None = None) -> list[AlertaResponseDTO]:
        """Evalúa todos los dispositivos activos en el sistema."""
        momento_actual = ahora or ahora_utc()
        alertas_generadas: list[AlertaDispositivo] = []

        for dev in self._repo_dispositivos.listar():
            alerta = self._evaluar_dispositivo(dev, momento_actual)
            if alerta:
                alertas_generadas.append(alerta)

        return [AlertaMapper.to_dto(a) for a in alertas_generadas]
