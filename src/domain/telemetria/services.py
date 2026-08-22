import cmath
import math
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from src.domain.telemetria.entities import (
    AlertaDispositivo,
    LecturaInstantanea,
    PlanTelemetria,
)
from src.domain.telemetria.value_objects import Corriente, PotenciaActiva, SeveridadAlerta


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


class FiltroPersistenciaTemporalService:
    """Filtro de persistencia temporal para evitar falsos positivos por transitorios (anti-alert fatigue).

    Una condición de subtensión o sobretensión solo debe disparar una AlertaDispositivo
    si persiste durante al menos `min_lecturas` consecutivas o `min_segundos` continuos.
    Thread-safe vía `threading.Lock`.
    """

    def __init__(self, min_lecturas: int = 2, min_segundos: float = 3.0):
        self._min_lecturas = min_lecturas
        self._min_segundos = min_segundos
        self._estados: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def procesar_alerta(
        self,
        dispositivo_id: str,
        alerta: AlertaDispositivo | None,
        categoria: str | None = None,
        ahora: datetime | None = None,
    ) -> AlertaDispositivo | None:
        """Evalúa si la anomalía cumple con el criterio de persistencia temporal.

        - Si `alerta` es None: la condición para esa `categoria` se normalizó; se resetea el estado correspondiente.
        - Si `alerta` es anómala:
            * 1ra lectura: se registra el inicio del evento; se retorna None (posible transitorio <2s).
            * 2da+ lecturas consecutivas (o delta_t >= min_segundos): se confirma la alerta y se retorna.
            * Episodio activo ya disparado: retorna None para evitar spam de alertas idénticas continuas,
              salvo que la severidad haya escalado a CRITICAL.
        """
        if ahora is None:
            ahora = alerta.disparada_en if alerta and alerta.disparada_en else datetime.now(timezone.utc)

        with self._lock:
            if alerta is None:
                if categoria:
                    if categoria.upper() == "TENSION":
                        self._estados.pop(f"{dispositivo_id}:BAJA_TENSION", None)
                        self._estados.pop(f"{dispositivo_id}:SOBRETENSION", None)
                    else:
                        self._estados.pop(f"{dispositivo_id}:{categoria}", None)
                else:
                    prefijo = f"{dispositivo_id}:"
                    claves = [k for k in self._estados if k == dispositivo_id or k.startswith(prefijo)]
                    for k in claves:
                        self._estados.pop(k, None)
                return None

            clave = f"{dispositivo_id}:{alerta.tipo_alerta}"
            # Si cambió el tipo de anomalía de tensión (ej. de BAJA a SOBRE), limpiar la contraria
            if alerta.tipo_alerta == "BAJA_TENSION":
                self._estados.pop(f"{dispositivo_id}:SOBRETENSION", None)
            elif alerta.tipo_alerta == "SOBRETENSION":
                self._estados.pop(f"{dispositivo_id}:BAJA_TENSION", None)

            estado = self._estados.get(clave)

            if estado is None:
                self._estados[clave] = {
                    "conteo": 1,
                    "primer_registro": ahora,
                    "ultimo_registro": ahora,
                    "disparada": False,
                    "severidad_disparada": None,
                }
                if self._min_lecturas <= 1:
                    self._estados[clave]["disparada"] = True
                    self._estados[clave]["severidad_disparada"] = alerta.severidad
                    return alerta
                return None

            estado["conteo"] += 1
            estado["ultimo_registro"] = ahora
            delta_seg = (ahora - estado["primer_registro"]).total_seconds()
            cumple_persistencia = (estado["conteo"] >= self._min_lecturas) or (delta_seg >= self._min_segundos)

            if not cumple_persistencia:
                return None

            if not estado["disparada"]:
                estado["disparada"] = True
                estado["severidad_disparada"] = alerta.severidad
                return alerta

            # Si ya fue disparada previamente en este episodio, solo permitir re-disparo si escaló a CRITICAL
            if (
                estado["severidad_disparada"] != SeveridadAlerta.CRITICAL
                and alerta.severidad == SeveridadAlerta.CRITICAL
            ):
                estado["severidad_disparada"] = SeveridadAlerta.CRITICAL
                return alerta

            return None

    def limpiar(self) -> None:
        """Vacía el registro de estados de persistencia."""
        with self._lock:
            self._estados.clear()


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
    def calcular_desbalance_tension(vr: float | None, vs: float | None, vt: float | None) -> float | None:
        """Calcula el Desbalance de Tensión Trifásico (VUR) según fórmula estándar NEMA/IEC.

        V_prom = (V_R + V_S + V_T) / 3
        VUR (%) = (max(|V_R - V_prom|, |V_S - V_prom|, |V_T - V_prom|) / V_prom) * 100
        """
        if vr is None or vs is None or vt is None:
            return None
        v_prom = (vr + vs + vt) / 3.0
        if v_prom <= 0.0:
            return None
        desv_max = max(abs(vr - v_prom), abs(vs - v_prom), abs(vt - v_prom))
        return round((desv_max / v_prom) * 100.0, 2)

    @staticmethod
    def calcular_corriente_neutro(
        ir: float | None,
        is_: float | None,
        it: float | None,
        pr: float | None = None,
        ps: float | None = None,
        pt: float | None = None,
        qr: float | None = None,
        qs: float | None = None,
        qt: float | None = None,
    ) -> Corriente | None:
        """Calcula la corriente de neutro estimada (RMS) mediante suma fasorial de Kirchhoff.

        I_N = - (I_R + I_S + I_T)
        Con desfase angular de 120° entre fases y ángulo de carga phi = atan2(Q, P).
        """
        if ir is None or is_ is None or it is None:
            return None

        # Ángulos de tensión de referencia para secuencia positiva R-S-T
        th_vr = 0.0
        th_vs = -2.0 * math.pi / 3.0  # -120°
        th_vt = 2.0 * math.pi / 3.0   # +120°

        # Desfase corriente-tensión phi = atan2(Q, P)
        def _calc_phi(p: float | None, q: float | None) -> float:
            if p is None or q is None:
                return 0.0
            if p == 0.0 and q == 0.0:
                return 0.0
            return math.atan2(q, p)

        phi_r = _calc_phi(pr, qr)
        phi_s = _calc_phi(ps, qs)
        phi_t = _calc_phi(pt, qt)

        # Fasores de corriente
        i_r = cmath.rect(ir, th_vr - phi_r)
        i_s = cmath.rect(is_, th_vs - phi_s)
        i_t = cmath.rect(it, th_vt - phi_t)

        i_n = -(i_r + i_s + i_t)
        in_rms = round(abs(i_n), 2)
        return Corriente(amperios=in_rms)

    @staticmethod
    def evaluar_alerta_desbalance(
        dispositivo_id: str,
        lectura: LecturaInstantanea,
        umbral_warning: float = 2.0,
        umbral_critico: float = 3.0,
    ) -> AlertaDispositivo | None:
        """Evalúa desbalance trifásico (VUR) y genera AlertaDispositivo si supera umbrales."""
        vur = lectura.desbalance_tension_porcentaje
        if vur is None:
            vr = lectura.fase_r.tension.voltios if lectura.fase_r.tension else None
            vs = lectura.fase_s.tension.voltios if lectura.fase_s.tension else None
            vt = lectura.fase_t.tension.voltios if lectura.fase_t.tension else None
            vur = AnalizadorCalidadEnergiaService.calcular_desbalance_tension(vr, vs, vt)

        if vur is None:
            return None

        if vur > umbral_critico:
            return AlertaDispositivo(
                id=None,
                dispositivo_id=dispositivo_id,
                tipo_alerta="DESBALANCE_TENSION",
                severidad=SeveridadAlerta.CRITICAL,
                mensaje=f"Desbalance de tensión superior al límite normativo del 2%: {vur}%",
            )
        elif vur > umbral_warning:
            return AlertaDispositivo(
                id=None,
                dispositivo_id=dispositivo_id,
                tipo_alerta="DESBALANCE_TENSION",
                severidad=SeveridadAlerta.WARNING,
                mensaje=f"Desbalance de tensión superior al límite normativo del 2%: {vur}%",
            )
        return None

    @staticmethod
    def evaluar_alerta_tension(
        dispositivo_id: str,
        lectura: LecturaInstantanea,
        umbral_baja_critica: float = 190.0,
        umbral_baja_warning: float = 198.0,
        umbral_alta_warning: float = 242.0,
        umbral_alta_critica: float = 248.0,
    ) -> AlertaDispositivo | None:
        """Esquema de Alertas de Tensión de Dos Niveles (Norma ENRE vs. Peligro Crítico).

        - Nivel 1 (Advertencia Contractual ENRE ±10%):
          * Subtensión: V < 198.0V (WARNING)
          * Sobretensión: V > 242.0V (WARNING)
        - Nivel 2 (Peligro Crítico de Equipo / Riesgo Térmico y Dieléctrico):
          * Subtensión Crítica: V < 190.0V (CRITICAL)
          * Sobretensión Crítica: V > 248.0V (CRITICAL)
        """
        fases = [("R", lectura.fase_r.tension), ("S", lectura.fase_s.tension), ("T", lectura.fase_t.tension)]

        # 1. Prioridad: Verificar si existe condición CRITICAL en alguna fase
        for nombre_fase, tension_obj in fases:
            if tension_obj is not None:
                v = tension_obj.voltios
                if v < umbral_baja_critica:
                    return AlertaDispositivo(
                        id=None,
                        dispositivo_id=dispositivo_id,
                        tipo_alerta="BAJA_TENSION",
                        severidad=SeveridadAlerta.CRITICAL,
                        mensaje=f"Baja tensión detectada en Fase {nombre_fase}: {v}V (Mínimo: {umbral_baja_critica}V)",
                    )
                elif v > umbral_alta_critica:
                    return AlertaDispositivo(
                        id=None,
                        dispositivo_id=dispositivo_id,
                        tipo_alerta="SOBRETENSION",
                        severidad=SeveridadAlerta.CRITICAL,
                        mensaje=f"Sobretensión detectada en Fase {nombre_fase}: {v}V (Máximo: {umbral_alta_critica}V)",
                    )

        # 2. Verificar condiciones WARNING (Norma ENRE)
        for nombre_fase, tension_obj in fases:
            if tension_obj is not None:
                v = tension_obj.voltios
                if v < umbral_baja_warning:
                    return AlertaDispositivo(
                        id=None,
                        dispositivo_id=dispositivo_id,
                        tipo_alerta="BAJA_TENSION",
                        severidad=SeveridadAlerta.WARNING,
                        mensaje=f"Baja tensión detectada en Fase {nombre_fase}: {v}V (Mínimo: {umbral_baja_warning}V)",
                    )
                elif v > umbral_alta_warning:
                    return AlertaDispositivo(
                        id=None,
                        dispositivo_id=dispositivo_id,
                        tipo_alerta="SOBRETENSION",
                        severidad=SeveridadAlerta.WARNING,
                        mensaje=f"Sobretensión detectada en Fase {nombre_fase}: {v}V (Máximo: {umbral_alta_warning}V)",
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
