"""src/domain/telemetria/servicios/politicas_suscripcion.py."""

from datetime import datetime, timedelta, timezone

from src.domain.telemetria.entities import PlanTelemetria
from src.domain.telemetria.value_objects import ModoFreeTier


class PoliticaRetencionService:
    @staticmethod
    def ventana_consulta(plan: PlanTelemetria, ahora: datetime) -> datetime:
        return ahora - timedelta(days=plan.retencion_dias)

    @staticmethod
    def fecha_corte_telemetria(plan: PlanTelemetria, ahora: datetime) -> datetime:
        return ahora - timedelta(days=plan.retencion_dias)

    @staticmethod
    def fecha_corte_status_logs(ahora: datetime, dias: int = 7) -> datetime:
        return ahora - timedelta(days=dias)

    @staticmethod
    def fecha_corte_alertas_resueltas(ahora: datetime, dias: int = 30) -> datetime:
        return ahora - timedelta(days=dias)


class PoliticaSuscripcionService:
    """Reglas de vigencia del plan pago único y de la política Free por defecto.

    Sin PRO vigente, la organización opera en modo Free: 7 días de retención,
    granularidad mínima de 1 hora, sin notificaciones.
    """

    @staticmethod
    def _normalizar_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def es_pro_vigente(vencimiento: datetime | None, ahora: datetime) -> bool:
        if vencimiento is None:
            return False
        v_utc = PoliticaSuscripcionService._normalizar_utc(vencimiento)
        a_utc = PoliticaSuscripcionService._normalizar_utc(ahora)
        return a_utc <= v_utc

    @staticmethod
    def es_enterprise_vigente(vencimiento: datetime, ahora: datetime) -> bool:
        return PoliticaSuscripcionService.es_pro_vigente(vencimiento, ahora)

    @staticmethod
    def resolver_retencion_dias(es_pro: bool, modo_free: ModoFreeTier) -> int:
        if es_pro:
            return 365
        if modo_free == ModoFreeTier.VITRINA_ANONIMA:
            return 30
        return 7

    @staticmethod
    def resolver_intervalo_minimo_segundos(es_pro: bool, modo_free: ModoFreeTier) -> int:
        if es_pro or modo_free == ModoFreeTier.VITRINA_ANONIMA:
            return 0
        return 3600  # En Privado Básico la granularidad mínima es de 1 hora
