import cmath
import math
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from src.domain.telemetria.entities import (
    AlertaDispositivo,
    LecturaInstantanea,
    MedicionFase,
    PlanTelemetria,
)
from src.domain.telemetria.value_objects import (
    Corriente,
    FactorPotencia,
    PotenciaActiva,
    PotenciaAparente,
    PotenciaReactiva,
    SeveridadAlerta,
    Tension,
)


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
        th_vt = 2.0 * math.pi / 3.0  # +120°

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
    def calcular_tension_neutro(
        vr: float | None,
        vs: float | None,
        vt: float | None,
        ir: float | None,
        is_: float | None,
        it: float | None,
        pr: float | None = None,
        ps: float | None = None,
        pt: float | None = None,
        qr: float | None = None,
        qs: float | None = None,
        qt: float | None = None,
    ) -> float | None:
        """Calcula la tensión de neutro estimada (RMS) mediante suma fasorial de Kirchhoff.

        V_N = - (V_R + V_S + V_T) / 3
        Considerando desfase angular de 120° entre fases y ángulo de carga phi = atan2(Q, P).
        """
        if vr is None or vs is None or vt is None:
            return None

        # Ángulos de tensión de referencia para secuencia positiva R-S-T
        th_vr = 0.0
        th_vs = -2.0 * math.pi / 3.0  # -120°
        th_vt = 2.0 * math.pi / 3.0  # +120°

        # Fasores de tensión
        v_r = cmath.rect(vr, th_vr)
        v_s = cmath.rect(vs, th_vs)
        v_t = cmath.rect(vt, th_vt)

        # Tensión de neutro estimada: V_N = - (V_R + V_S + V_T) / 3 + Z_N * I_N
        # Asumiendo Z_N despreciable, simplificamos a V_N = - (V_R + V_S + V_T) / 3
        v_n = -(v_r + v_s + v_t) / 3.0
        vn_rms = round(abs(v_n), 2)
        return vn_rms

    @classmethod
    def _agregar_grupo_lecturas(
        cls,
        items: list[LecturaInstantanea],
        bucket_dt: datetime,
    ) -> LecturaInstantanea:
        dispositivo_id = items[0].dispositivo_id

        def _avg(vals: list[float | None]) -> float | None:
            non_none = [v for v in vals if v is not None]
            if not non_none:
                return None
            return round(sum(non_none) / len(non_none), 2)

        def _fase_agregada(fases: list[MedicionFase]) -> MedicionFase:
            v = _avg([f.tension.voltios for f in fases if f.tension])
            i = _avg([f.corriente.amperios for f in fases if f.corriente])
            p = _avg([f.potencia_activa.vatios for f in fases if f.potencia_activa])
            q = _avg([f.potencia_reactiva.var for f in fases if f.potencia_reactiva])
            s = _avg([f.potencia_aparente.va for f in fases if f.potencia_aparente])
            if s is None and p is not None and q is not None:
                s = round(math.hypot(p, q), 2)
            fp: float | None = None
            if p is not None and s is not None and s > 0:
                fp = round(p / s, 2)
            else:
                fp = _avg([f.factor_potencia.valor for f in fases if f.factor_potencia])
            return MedicionFase(
                tension=Tension(voltios=v) if v is not None else None,
                corriente=Corriente(amperios=i) if i is not None else None,
                potencia_activa=PotenciaActiva(vatios=p) if p is not None else None,
                potencia_reactiva=PotenciaReactiva(var=q) if q is not None else None,
                potencia_aparente=PotenciaAparente(va=s) if s is not None else None,
                factor_potencia=FactorPotencia(valor=fp) if fp is not None else None,
            )

        fase_r = _fase_agregada([it.fase_r for it in items])
        fase_s = _fase_agregada([it.fase_s for it in items])
        fase_t = _fase_agregada([it.fase_t for it in items])

        p_tot = _avg([it.potencia_activa_total.vatios for it in items if it.potencia_activa_total])
        if p_tot is None:
            p_sub = [f.potencia_activa.vatios for f in (fase_r, fase_s, fase_t) if f.potencia_activa]
            if p_sub:
                p_tot = round(sum(p_sub), 2)

        q_tot = _avg([it.potencia_reactiva_total.var for it in items if it.potencia_reactiva_total])
        if q_tot is None:
            q_sub = [f.potencia_reactiva.var for f in (fase_r, fase_s, fase_t) if f.potencia_reactiva]
            if q_sub:
                q_tot = round(sum(q_sub), 2)

        s_tot = _avg([it.potencia_aparente_total.va for it in items if it.potencia_aparente_total])
        if s_tot is None and p_tot is not None and q_tot is not None:
            s_tot = round(math.hypot(p_tot, q_tot), 2)

        fp_tot: float | None = None
        if p_tot is not None and s_tot is not None and s_tot > 0:
            fp_tot = round(p_tot / s_tot, 2)
        else:
            fp_tot = _avg([it.factor_potencia_total.valor for it in items if it.factor_potencia_total])

        vr = fase_r.tension.voltios if fase_r.tension else None
        vs = fase_s.tension.voltios if fase_s.tension else None
        vt = fase_t.tension.voltios if fase_t.tension else None
        desbalance_v = cls.calcular_desbalance_tension(vr, vs, vt)

        tensiones_fase = [v for v in (vr, vs, vt) if v is not None]
        voltage_linea_V = None
        if tensiones_fase:
            promedio_fase = sum(tensiones_fase) / len(tensiones_fase)
            voltage_linea_V = round(promedio_fase * 1.7320508075688772, 2)

        ir_val = fase_r.corriente.amperios if fase_r.corriente else None
        is_val = fase_s.corriente.amperios if fase_s.corriente else None
        it_val = fase_t.corriente.amperios if fase_t.corriente else None
        pr_val = fase_r.potencia_activa.vatios if fase_r.potencia_activa else None
        ps_val = fase_s.potencia_activa.vatios if fase_s.potencia_activa else None
        pt_val = fase_t.potencia_activa.vatios if fase_t.potencia_activa else None
        qr_val = fase_r.potencia_reactiva.var if fase_r.potencia_reactiva else None
        qs_val = fase_s.potencia_reactiva.var if fase_s.potencia_reactiva else None
        qt_val = fase_t.potencia_reactiva.var if fase_t.potencia_reactiva else None

        i_neutro = cls.calcular_corriente_neutro(ir_val, is_val, it_val, pr_val, ps_val, pt_val, qr_val, qs_val, qt_val)
        v_neutro = cls.calcular_tension_neutro(
            vr, vs, vt, ir_val, is_val, it_val, pr_val, ps_val, pt_val, qr_val, qs_val, qt_val
        )

        return LecturaInstantanea(
            id=None,
            dispositivo_id=dispositivo_id,
            registrado_en=bucket_dt,
            fase_r=fase_r,
            fase_s=fase_s,
            fase_t=fase_t,
            potencia_activa_total=PotenciaActiva(vatios=p_tot) if p_tot is not None else None,
            potencia_reactiva_total=PotenciaReactiva(var=q_tot) if q_tot is not None else None,
            potencia_aparente_total=PotenciaAparente(va=s_tot) if s_tot is not None else None,
            factor_potencia_total=FactorPotencia(valor=fp_tot) if fp_tot is not None else None,
            desbalance_tension_porcentaje=desbalance_v,
            corriente_neutro_estimada=i_neutro,
            voltage_linea_V=voltage_linea_V,
            tension_neutro_estimada=v_neutro,
        )

    @classmethod
    def agregar_lecturas_en_intervalo(
        cls,
        lecturas: list[LecturaInstantanea],
        intervalo_segundos: int,
    ) -> list[LecturaInstantanea]:
        """Agrupa y remuestrea una lista de LecturaInstantanea en buckets de tiempo fijos."""
        if intervalo_segundos <= 0 or not lecturas:
            return lecturas

        buckets: dict[int, list[LecturaInstantanea]] = {}
        for item in lecturas:
            ts = item.registrado_en.timestamp()
            bucket_ts = int(ts // intervalo_segundos) * intervalo_segundos
            if bucket_ts not in buckets:
                buckets[bucket_ts] = []
            buckets[bucket_ts].append(item)

        resultado = []
        for bucket_ts in sorted(buckets.keys(), reverse=True):
            bucket_items = buckets[bucket_ts]
            bucket_dt = datetime.fromtimestamp(bucket_ts, tz=timezone.utc)
            agregada = cls._agregar_grupo_lecturas(bucket_items, bucket_dt)
            resultado.append(agregada)

        return resultado

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

    @staticmethod
    def evaluar_alerta_ti_invertido(
        dispositivo_id: str,
        lectura: LecturaInstantanea,
        tipo_instalacion: str = "CONSUMO",
        fases_con_ti: list[str] | set[str] | None = None,
        umbral_corriente_minima: float = 5.0,
        umbral_potencia_negativa: float = -500.0,
    ) -> list[AlertaDispositivo]:
        """Evalúa si algún TI está invertido físicamente en una instalación de consumo puro.

        Si la instalación es de GENERACION_FV o MIXTO, no se genera alerta ya que la
        potencia negativa representa exportación legítima hacia la red.
        """
        if tipo_instalacion != "CONSUMO":
            return []

        fases_activas = set(fases_con_ti) if fases_con_ti is not None else {"R", "S", "T"}
        alertas: list[AlertaDispositivo] = []

        fases = [
            ("R", lectura.fase_r),
            ("S", lectura.fase_s),
            ("T", lectura.fase_t),
        ]

        for nombre_fase, med in fases:
            if nombre_fase not in fases_activas:
                continue

            i_val = med.corriente.amperios if med.corriente else 0.0
            p_val = med.potencia_activa.vatios if med.potencia_activa else 0.0

            if i_val >= umbral_corriente_minima and p_val <= umbral_potencia_negativa:
                alertas.append(
                    AlertaDispositivo(
                        id=None,
                        dispositivo_id=dispositivo_id,
                        tipo_alerta="TI_INVERTIDO",
                        severidad=SeveridadAlerta.WARNING,
                        mensaje=(
                            f"Posible inversión de polaridad en Transformador de Corriente (TI) de Fase {nombre_fase}: "
                            f"P={p_val}W, I={i_val}A. "
                            f"Verificar el sentido de la flecha física o invertir la polaridad por software en 192.168.4.1."
                        ),
                    )
                )

        return alertas


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
    """Reglas de ciclo de vida del Plan Enterprise y transición a Freemium.

    - Toda nueva instalación incluye 12 meses (365 días) de Plan Enterprise.
    - Cada consultoría de eficiencia energética añade +1 mes (30 días) de Plan Enterprise.
    - Vencido el plazo sin consultoría, la organización pasa al Plan 0 (Freemium).
    """

    DURACION_INSTALACION_INICIAL_DIAS: int = 365
    DURACION_CONSULTORIA_DIAS: int = 30

    @staticmethod
    def calcular_vencimiento_inicial(fecha_instalacion: datetime) -> datetime:
        return fecha_instalacion + timedelta(days=365)

    @staticmethod
    def extender_por_consultoria(vencimiento_actual: datetime, fecha_consultoria: datetime) -> datetime:
        base = max(vencimiento_actual, fecha_consultoria)
        return base + timedelta(days=30)

    @staticmethod
    def es_enterprise_vigente(vencimiento: datetime, ahora: datetime) -> bool:
        return ahora <= vencimiento
