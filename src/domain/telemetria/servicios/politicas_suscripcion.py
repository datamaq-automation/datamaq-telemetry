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
    """Reglas de ciclo de vida del Plan PRO y transición al modelo Freemium bifurcado.

    - Toda nueva instalación incluye 60 días (2 meses) de Plan PRO.
    - Cada consultoría garantiza 60 días de Plan PRO a partir de la fecha de realización (no acumulable).
    - Vencido el plazo sin consultoría, la organización pasa al modo Free configurado (PRIVADO_BASICO por defecto o VITRINA_ANONIMA).
    """

    DURACION_INSTALACION_INICIAL_DIAS: int = 60
    DURACION_CONSULTORIA_DIAS: int = 60

    @staticmethod
    def _normalizar_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def calcular_vencimiento_inicial(fecha_instalacion: datetime) -> datetime:
        return fecha_instalacion + timedelta(days=PoliticaSuscripcionService.DURACION_INSTALACION_INICIAL_DIAS)

    @staticmethod
    def extender_por_consultoria(vencimiento_actual: datetime, fecha_consultoria: datetime) -> datetime:
        v_act = PoliticaSuscripcionService._normalizar_utc(vencimiento_actual)
        f_cons = PoliticaSuscripcionService._normalizar_utc(fecha_consultoria)
        nuevo_vencimiento = f_cons + timedelta(days=PoliticaSuscripcionService.DURACION_CONSULTORIA_DIAS)
        res = max(v_act, nuevo_vencimiento)
        return res if vencimiento_actual.tzinfo is not None else res.replace(tzinfo=None)

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
        return 14

    @staticmethod
    def resolver_intervalo_minimo_segundos(es_pro: bool, modo_free: ModoFreeTier) -> int:
        if es_pro or modo_free == ModoFreeTier.VITRINA_ANONIMA:
            return 0
        return 3600  # En Privado Básico la granularidad mínima es de 1 hora
