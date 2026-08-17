import threading
from datetime import datetime, timedelta, timezone

from src.domain.telemetria.entities import (
    AlertaDispositivo,
    LecturaInstantanea,
    PlanTelemetria,
)
from src.domain.telemetria.value_objects import PotenciaActiva, SeveridadAlerta


class FiltroDeduplicacionService:
    """Filtro de deduplicación de mensajes MQTT (at-least-once → exactly-once).

    Registra las claves vistas y descarta las que se repiten dentro de la
    ventana temporal configurada. Thread-safe vía un ``threading.Lock`` interno.
    """

    def __init__(self, ventana_segundos: int = 120):
        self._ventana_segundos = ventana_segundos
        self._vistos: dict[str, datetime] = {}
        self._lock = threading.Lock()

    def es_duplicado(self, clave: str, ahora: datetime | None = None) -> bool:
        """Retorna ``True`` si ``clave`` ya fue vista dentro de la ventana.

        En caso contrario, la registra y retorna ``False``. Poda las entradas
        vencidas en cada invocación.
        """
        if ahora is None:
            ahora = datetime.now(timezone.utc)
        with self._lock:
            self._podar(ahora)
            if clave in self._vistos:
                return True
            self._vistos[clave] = ahora
            return False

    def limpiar(self) -> None:
        """Vacía el registro de claves vistas."""
        with self._lock:
            self._vistos.clear()

    def _podar(self, ahora: datetime) -> None:
        limite = ahora - timedelta(seconds=self._ventana_segundos)
        self._vistos = {k: v for k, v in self._vistos.items() if v > limite}


class AnalizadorCalidadEnergiaService:
    """Servicio de dominio puro para validar balances y detectar anomalías en mediciones."""

    @staticmethod
    def calcular_potencia_trifasica_activa(
        pr: float | None, ps: float | None, pt: float | None
    ) -> PotenciaActiva | None:
        valores = [v for v in (pr, ps, pt) if v is not None]
        if not valores:
            return None
        return PotenciaActiva(vatios=round(sum(valores), 2))

    @staticmethod
    def evaluar_alerta_tension(
        dispositivo_id: str, lectura: LecturaInstantanea, umbral_baja: float = 190.0, umbral_alta: float = 245.0
    ) -> AlertaDispositivo | None:
        fases = [("R", lectura.fase_r.tension), ("S", lectura.fase_s.tension), ("T", lectura.fase_t.tension)]
        for nombre_fase, tension_obj in fases:
            if tension_obj is not None:
                v = tension_obj.voltios
                if v < umbral_baja:
                    return AlertaDispositivo(
                        id=None,
                        dispositivo_id=dispositivo_id,
                        tipo_alerta="BAJA_TENSION",
                        severidad=SeveridadAlerta.WARNING,
                        mensaje=f"Baja tensión detectada en Fase {nombre_fase}: {v}V (Mínimo: {umbral_baja}V)",
                    )
                elif v > umbral_alta:
                    return AlertaDispositivo(
                        id=None,
                        dispositivo_id=dispositivo_id,
                        tipo_alerta="SOBRETENSION",
                        severidad=SeveridadAlerta.CRITICAL,
                        mensaje=f"Sobretensión detectada en Fase {nombre_fase}: {v}V (Máximo: {umbral_alta}V)",
                    )
        return None


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
