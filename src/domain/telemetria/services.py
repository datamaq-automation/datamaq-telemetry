import cmath
import math
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from src.domain.telemetria.analizador_reactiva import DimensionadorCompensacionService
from src.domain.telemetria.entities import (
    AlertaDispositivo,
    LecturaInstantanea,
    MedicionFase,
    PlanTelemetria,
)
from src.domain.telemetria.value_objects import (
    AnaliticaCalidadEnergia,
    Corriente,
    EstadoFactorPotencia,
    EstadoTension,
    FactorPotencia,
    ModoFreeTier,
    PotenciaActiva,
    PotenciaAparente,
    PotenciaReactiva,
    SeveridadAlerta,
    Tension,
)


class CalculadoraPotenciaService:
    """Cálculo canónico de potencia aparente y factor de potencia.

    El firmware Powermeter publica el formato compacto `{"n":"R","v":..,"i":..,"p":..,"q":..}`,
    sin potencia aparente. Antes nadie la derivaba en la ingesta y la agregación la
    aproximaba con `hypot(P, Q)`, así que una consulta `raw` devolvía `null` donde la
    agregada devolvía un número, y con dos definiciones distintas.

    Se unifica en `S = V_rms · I_rms`, que es la definición exacta de potencia aparente.
    A diferencia de `hypot(P, Q)`, incluye la potencia de distorsión, que en cargas
    conmutadas es sustancial: para una fase con V=227.7, I=0.9, P=147 y Q=-51, `hypot`
    da FP 0.94 mientras que V·I da 0.72. La diferencia es real y estaba invisible.
    """

    @staticmethod
    def calcular_potencia_aparente(tension_v: float | None, corriente_a: float | None) -> float | None:
        """S = |V| · |I| en VA. `None` si falta cualquiera de los dos factores.

        Cero es un resultado válido —significa que no hay carga—, no un dato ausente.
        """
        if tension_v is None or corriente_a is None:
            return None
        return round(abs(tension_v) * abs(corriente_a), 2)

    @staticmethod
    def calcular_factor_potencia(
        potencia_activa_w: float | None,
        potencia_aparente_va: float | None,
    ) -> float | None:
        """FP = P / S, acotado a [-1, 1]. `None` si falta un término o si S <= 0.

        Sin potencia aparente el factor de potencia es indefinido, no óptimo: devolver
        1.0 sería la misma mentira optimista que arrastraba `determinar_estado_fp`.

        El acotado no es cosmético. `FactorPotencia` rechaza valores fuera de [-1, 1],
        y `S = V·I` se calcula con tensión y corriente redondeadas a dos decimales por
        el firmware, mientras que P se mide aparte: el cociente puede superar 1 por
        redondeo y hacer fallar la ingesta entera.

        Se preserva el signo de P, que distingue consumo de exportación (o un TI invertido).
        """
        if potencia_activa_w is None or potencia_aparente_va is None:
            return None
        if potencia_aparente_va <= 0.0:
            return None
        fp = potencia_activa_w / potencia_aparente_va
        return round(max(-1.0, min(1.0, fp)), 2)

    @staticmethod
    def calcular_potencia_aparente_total(*aparentes: float | None) -> float | None:
        """Potencia aparente aritmética trifásica: suma de las S de fase presentes."""
        presentes = [s for s in aparentes if s is not None]
        if not presentes:
            return None
        return round(sum(presentes), 2)


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
                    if categoria.upper() in ("TENSION", "SUMINISTRO"):
                        self._estados.pop(f"{dispositivo_id}:BAJA_TENSION", None)
                        self._estados.pop(f"{dispositivo_id}:SOBRETENSION", None)
                        self._estados.pop(f"{dispositivo_id}:FALTA_FASE", None)
                    else:
                        self._estados.pop(f"{dispositivo_id}:{categoria}", None)
                else:
                    prefijo = f"{dispositivo_id}:"
                    claves = [k for k in self._estados if k == dispositivo_id or k.startswith(prefijo)]
                    for k in claves:
                        self._estados.pop(k, None)
                return None

            clave = f"{dispositivo_id}:{alerta.tipo_alerta}"
            # Si cambió el tipo de anomalía de tensión/suministro, limpiar los contrarios
            if alerta.tipo_alerta == "BAJA_TENSION":
                self._estados.pop(f"{dispositivo_id}:SOBRETENSION", None)
                self._estados.pop(f"{dispositivo_id}:FALTA_FASE", None)
            elif alerta.tipo_alerta == "SOBRETENSION":
                self._estados.pop(f"{dispositivo_id}:BAJA_TENSION", None)
                self._estados.pop(f"{dispositivo_id}:FALTA_FASE", None)
            elif alerta.tipo_alerta == "FALTA_FASE":
                self._estados.pop(f"{dispositivo_id}:BAJA_TENSION", None)
                self._estados.pop(f"{dispositivo_id}:SOBRETENSION", None)

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
                alerta.disparada_en = estado["primer_registro"]
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
            thd_v = _avg([f.thd_v_porcentaje for f in fases if f.thd_v_porcentaje is not None])
            thd_i = _avg([f.thd_i_porcentaje for f in fases if f.thd_i_porcentaje is not None])
            return MedicionFase(
                tension=Tension(voltios=v) if v is not None else None,
                corriente=Corriente(amperios=i) if i is not None else None,
                potencia_activa=PotenciaActiva(vatios=p) if p is not None else None,
                potencia_reactiva=PotenciaReactiva(var=q) if q is not None else None,
                potencia_aparente=PotenciaAparente(va=s) if s is not None else None,
                factor_potencia=FactorPotencia(valor=fp) if fp is not None else None,
                thd_v_porcentaje=thd_v,
                thd_i_porcentaje=thd_i,
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

        thd_v_prom = _avg([it.thd_v_promedio_porcentaje for it in items if it.thd_v_promedio_porcentaje is not None])
        if thd_v_prom is None:
            thd_v_vals = [
                (f.thd_v_porcentaje if f.thd_v_porcentaje is not None else f.thd_v_pct)
                for f in (fase_r, fase_s, fase_t)
                if (f.thd_v_porcentaje is not None or f.thd_v_pct is not None)
            ]
            if thd_v_vals:
                thd_v_prom = _avg(thd_v_vals)

        thd_i_tot = _avg([it.thd_i_total_porcentaje for it in items if it.thd_i_total_porcentaje is not None])
        if thd_i_tot is None:
            thd_i_vals = [
                (f.thd_i_porcentaje if f.thd_i_porcentaje is not None else f.thd_i_pct)
                for f in (fase_r, fase_s, fase_t)
                if (f.thd_i_porcentaje is not None or f.thd_i_pct is not None)
            ]
            if thd_i_vals:
                thd_i_tot = _avg(thd_i_vals)

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
            thd_v_promedio_porcentaje=thd_v_prom,
            thd_i_total_porcentaje=thd_i_tot,
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
            reg = item.registrado_en
            if reg.tzinfo is None:
                reg = reg.replace(tzinfo=timezone.utc)
            ts = reg.timestamp()
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
        vr = lectura.fase_r.tension.voltios if lectura.fase_r.tension else None
        vs = lectura.fase_s.tension.voltios if lectura.fase_s.tension else None
        vt = lectura.fase_t.tension.voltios if lectura.fase_t.tension else None

        # Jerarquía de fallas: Si alguna fase está caída (< 50V / Falta de Suministro),
        # se inhibe la alerta de desbalance para priorizar la alarma de FALTA_FASE.
        if any(v is not None and v < 50.0 for v in (vr, vs, vt)):
            return None

        vur = lectura.desbalance_tension_porcentaje
        if vur is None:
            vur = AnalizadorCalidadEnergiaService.calcular_desbalance_tension(vr, vs, vt)

        if vur is None:
            return None

        t_disparo = (
            lectura.registrado_en if (lectura and lectura.registrado_en is not None) else datetime.now(timezone.utc)
        )

        if vur > umbral_critico:
            return AlertaDispositivo(
                id=None,
                dispositivo_id=dispositivo_id,
                tipo_alerta="DESBALANCE_TENSION",
                severidad=SeveridadAlerta.CRITICAL,
                mensaje=f"Desbalance de tensión superior al límite normativo del 2%: {vur}%",
                disparada_en=t_disparo,
                fase="3F",
                valor_medido=vur,
                valor_umbral=umbral_critico,
                unidad="%",
                categoria="DESBALANCE_TENSION",
            )
        elif vur > umbral_warning:
            return AlertaDispositivo(
                id=None,
                dispositivo_id=dispositivo_id,
                tipo_alerta="DESBALANCE_TENSION",
                severidad=SeveridadAlerta.WARNING,
                mensaje=f"Desbalance de tensión superior al límite normativo del 2%: {vur}%",
                disparada_en=t_disparo,
                fase="3F",
                valor_medido=vur,
                valor_umbral=umbral_warning,
                unidad="%",
                categoria="DESBALANCE_TENSION",
            )
        return None

    @staticmethod
    def evaluar_alerta_tension(
        dispositivo_id: str,
        lectura: LecturaInstantanea,
        umbral_falta_fase: float = 50.0,
        umbral_baja_critica: float = 190.0,
        umbral_baja_warning: float = 198.0,
        umbral_alta_warning: float = 242.0,
        umbral_alta_critica: float = 248.0,
    ) -> AlertaDispositivo | None:
        """Esquema de Alertas de Tensión de Dos Niveles (Norma ENRE vs. Peligro Crítico).

        - Falta de Fase / Corte de Suministro: V < 50.0V (CRITICAL)
        - Nivel 1 (Advertencia Contractual ENRE ±10%):
          * Subtensión: V < 198.0V (WARNING)
          * Sobretensión: V > 242.0V (WARNING)
        - Nivel 2 (Peligro Crítico de Equipo / Riesgo Térmico y Dieléctrico):
          * Subtensión Crítica: V < 190.0V (CRITICAL)
          * Sobretensión Crítica: V > 248.0V (CRITICAL)
        """
        fases = [("R", lectura.fase_r.tension), ("S", lectura.fase_s.tension), ("T", lectura.fase_t.tension)]
        t_disparo = (
            lectura.registrado_en if (lectura and lectura.registrado_en is not None) else datetime.now(timezone.utc)
        )

        # 0. Corte de fase / Falta de suministro (V < 50V)
        for nombre_fase, tension_obj in fases:
            if tension_obj is not None:
                v = tension_obj.voltios
                if v < umbral_falta_fase:
                    return AlertaDispositivo(
                        id=None,
                        dispositivo_id=dispositivo_id,
                        tipo_alerta="FALTA_FASE",
                        severidad=SeveridadAlerta.CRITICAL,
                        mensaje=f"Falta de fase o corte de suministro en Fase {nombre_fase}: {v}V (Mínimo: {umbral_falta_fase}V)",
                        disparada_en=t_disparo,
                        fase=nombre_fase,
                        valor_medido=v,
                        valor_umbral=umbral_falta_fase,
                        unidad="V",
                        categoria="SUMINISTRO",
                    )

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
                        disparada_en=t_disparo,
                        fase=nombre_fase,
                        valor_medido=v,
                        valor_umbral=umbral_baja_critica,
                        unidad="V",
                        categoria="TENSION",
                    )
                elif v > umbral_alta_critica:
                    return AlertaDispositivo(
                        id=None,
                        dispositivo_id=dispositivo_id,
                        tipo_alerta="SOBRETENSION",
                        severidad=SeveridadAlerta.CRITICAL,
                        mensaje=f"Sobretensión detectada en Fase {nombre_fase}: {v}V (Máximo: {umbral_alta_critica}V)",
                        disparada_en=t_disparo,
                        fase=nombre_fase,
                        valor_medido=v,
                        valor_umbral=umbral_alta_critica,
                        unidad="V",
                        categoria="TENSION",
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
                        disparada_en=t_disparo,
                        fase=nombre_fase,
                        valor_medido=v,
                        valor_umbral=umbral_baja_warning,
                        unidad="V",
                        categoria="TENSION",
                    )
                elif v > umbral_alta_warning:
                    return AlertaDispositivo(
                        id=None,
                        dispositivo_id=dispositivo_id,
                        tipo_alerta="SOBRETENSION",
                        severidad=SeveridadAlerta.WARNING,
                        mensaje=f"Sobretensión detectada en Fase {nombre_fase}: {v}V (Máximo: {umbral_alta_warning}V)",
                        disparada_en=t_disparo,
                        fase=nombre_fase,
                        valor_medido=v,
                        valor_umbral=umbral_alta_warning,
                        unidad="V",
                        categoria="TENSION",
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
        """Evalúa si algún TI está invertido físicamente en una instalación de consumo puro."""
        if tipo_instalacion != "CONSUMO":
            return []

        fases_activas = set(fases_con_ti) if fases_con_ti is not None else {"R", "S", "T"}
        alertas: list[AlertaDispositivo] = []
        t_disparo = (
            lectura.registrado_en if (lectura and lectura.registrado_en is not None) else datetime.now(timezone.utc)
        )

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
                        disparada_en=t_disparo,
                        fase=nombre_fase,
                        valor_medido=p_val,
                        valor_umbral=umbral_potencia_negativa,
                        unidad="W",
                        categoria="TI_INVERTIDO",
                    )
                )

        return alertas

    @staticmethod
    def evaluar_alerta_factor_potencia(
        dispositivo_id: str,
        lectura: LecturaInstantanea,
        umbral_warning: float = 0.95,
        umbral_critico: float = 0.85,
        potencia_minima_w: float = 500.0,
    ) -> AlertaDispositivo | None:
        """Evalúa bajo factor de potencia (penalización tarifaria ENRE/distribuidoras)."""
        fp_obj = lectura.factor_potencia_total
        p_obj = lectura.potencia_activa_total
        if fp_obj is None or p_obj is None:
            return None

        # Solo evaluar si hay carga activa significativa para evitar falsas alarmas en vacío
        if p_obj.vatios < potencia_minima_w:
            return None

        fp = fp_obj.valor
        t_disparo = (
            lectura.registrado_en if (lectura and lectura.registrado_en is not None) else datetime.now(timezone.utc)
        )
        if fp < umbral_critico:
            return AlertaDispositivo(
                id=None,
                dispositivo_id=dispositivo_id,
                tipo_alerta="BAJO_FACTOR_POTENCIA",
                severidad=SeveridadAlerta.CRITICAL,
                mensaje=f"Factor de potencia crítico con penalización tarifaria: {fp} (Mínimo: {umbral_critico})",
                disparada_en=t_disparo,
                fase="TOTAL",
                valor_medido=fp,
                valor_umbral=umbral_critico,
                unidad="",
                categoria="FACTOR_POTENCIA",
            )
        elif fp < umbral_warning:
            return AlertaDispositivo(
                id=None,
                dispositivo_id=dispositivo_id,
                tipo_alerta="BAJO_FACTOR_POTENCIA",
                severidad=SeveridadAlerta.WARNING,
                mensaje=f"Factor de potencia por debajo del límite regulatorio ENRE: {fp} (Mínimo: {umbral_warning})",
                disparada_en=t_disparo,
                fase="TOTAL",
                valor_medido=fp,
                valor_umbral=umbral_warning,
                unidad="",
                categoria="FACTOR_POTENCIA",
            )
        return None

    @staticmethod
    def evaluar_alertas_distorsion_armonica(
        dispositivo_id: str,
        lectura: LecturaInstantanea,
        umbral_thd_v_warning: float = 5.0,
        umbral_thd_v_critico: float = 8.0,
        umbral_thd_i_warning: float = 20.0,
        umbral_corriente_minima_thd_i: float = 10.0,
        umbral_resonancia_thd_v: float = 4.0,
        umbral_resonancia_fp: float = 0.98,
    ) -> list[AlertaDispositivo]:
        """Evalúa anomalías por distorsión armónica total (THD) y riesgo de resonancia."""
        alertas: list[AlertaDispositivo] = []
        t_disparo = (
            lectura.registrado_en if (lectura and lectura.registrado_en is not None) else datetime.now(timezone.utc)
        )

        fases = [
            ("R", lectura.fase_r),
            ("S", lectura.fase_s),
            ("T", lectura.fase_t),
        ]

        # 1. Distorsión Armónica Total de Tensión (THD_V)
        for nombre_fase, med in fases:
            thd_v = med.thd_v_porcentaje if med.thd_v_porcentaje is not None else med.thd_v_pct
            if thd_v is not None:
                if thd_v > umbral_thd_v_critico:
                    alertas.append(
                        AlertaDispositivo(
                            id=None,
                            dispositivo_id=dispositivo_id,
                            tipo_alerta="ALTO_THD_TENSION_CRITICAL",
                            severidad=SeveridadAlerta.CRITICAL,
                            mensaje=f"THD de Tensión Crítico en Fase {nombre_fase}: {thd_v}% (Límite IEC: {umbral_thd_v_critico}%)",
                            disparada_en=t_disparo,
                            fase=nombre_fase,
                            valor_medido=thd_v,
                            valor_umbral=umbral_thd_v_critico,
                            unidad="%",
                            categoria="DISTORSION_ARMONICA",
                            observaciones="Peligro inminente de sobretensión armónica y daño en aislamientos de transformadores/motores.",
                        )
                    )
                elif thd_v > umbral_thd_v_warning:
                    alertas.append(
                        AlertaDispositivo(
                            id=None,
                            dispositivo_id=dispositivo_id,
                            tipo_alerta="ALTO_THD_TENSION_WARNING",
                            severidad=SeveridadAlerta.WARNING,
                            mensaje=f"THD de Tensión Elevado en Fase {nombre_fase}: {thd_v}% (Límite IEEE 519: {umbral_thd_v_warning}%)",
                            disparada_en=t_disparo,
                            fase=nombre_fase,
                            valor_medido=thd_v,
                            valor_umbral=umbral_thd_v_warning,
                            unidad="%",
                            categoria="DISTORSION_ARMONICA",
                            observaciones="Supera límite normativo. Verificar presencia de cargas no lineales o variadores de velocidad.",
                        )
                    )

        # 2. Distorsión Armónica Total de Corriente (THD_I con carga significativa)
        for nombre_fase, med in fases:
            thd_i = med.thd_i_porcentaje if med.thd_i_porcentaje is not None else med.thd_i_pct
            i_val = med.corriente.amperios if med.corriente else 0.0
            if thd_i is not None and i_val >= umbral_corriente_minima_thd_i:
                if thd_i > umbral_thd_i_warning:
                    alertas.append(
                        AlertaDispositivo(
                            id=None,
                            dispositivo_id=dispositivo_id,
                            tipo_alerta="ALTO_THD_CORRIENTE",
                            severidad=SeveridadAlerta.WARNING,
                            mensaje=f"Alta Distorsión de Corriente en Fase {nombre_fase}: {thd_i}% (Corriente: {i_val}A)",
                            disparada_en=t_disparo,
                            fase=nombre_fase,
                            valor_medido=thd_i,
                            valor_umbral=umbral_thd_i_warning,
                            unidad="%",
                            categoria="DISTORSION_ARMONICA",
                            observaciones="Riesgo de calentamiento excesivo en conductores, neutro y transformador aguas arriba.",
                        )
                    )

        # 3. Riesgo de Resonancia en Bancos de Capacitores (THD_V > 4.0% y FP >= 0.98)
        fp_tot = lectura.factor_potencia_total.valor if lectura.factor_potencia_total else None
        thd_v_vals = [
            float(value)
            for _, med in fases
            for value in [med.thd_v_porcentaje if med.thd_v_porcentaje is not None else med.thd_v_pct]
            if value is not None
        ]
        thd_v_max = max(thd_v_vals) if thd_v_vals else None
        thd_v_max_val = thd_v_max
        if fp_tot is not None and thd_v_max_val is not None:
            if abs(fp_tot) >= umbral_resonancia_fp and thd_v_max_val >= umbral_resonancia_thd_v:
                alertas.append(
                    AlertaDispositivo(
                        id=None,
                        dispositivo_id=dispositivo_id,
                        tipo_alerta="RIESGO_RESONANCIA_CAPACITORES",
                        severidad=SeveridadAlerta.WARNING,
                        mensaje=f"Riesgo de Resonancia Paralelo: THD_V={thd_v_max_val}% con FP={fp_tot}",
                        disparada_en=t_disparo,
                        fase="3F",
                        valor_medido=thd_v_max_val,
                        valor_umbral=umbral_resonancia_thd_v,
                        unidad="%",
                        categoria="DISTORSION_ARMONICA",
                        observaciones="FP unitario/cercano a la unidad con THD_V elevado sugiere amplificación armónica por banco de capacitores.",
                    )
                )

        return alertas

    @staticmethod
    def calcular_desbalance_corriente(
        ir: float | None,
        is_: float | None,
        it: float | None,
        umbral_corriente_minima: float = 5.0,
    ) -> float | None:
        """Calcula el Desbalance de Corriente Trifásico (IUR) según IEC 61000-4-30 / NEMA.

        I_prom = (I_R + I_S + I_T) / 3
        IUR (%) = (max(|I_R - I_prom|, |I_S - I_prom|, |I_T - I_prom|) / I_prom) * 100

        Por debajo de `umbral_corriente_minima` el indicador se satura con ruido: una
        instalación en standby con R=0.9 A y S/T en miliamperes daba 170% de desbalance,
        que no describe nada. Sin carga el IUR no es "0% de desbalance" sino "no medible",
        así que se devuelve `None`. El umbral sigue el precedente de la detección de TI
        invertido, que ya exige 5 A.
        """
        if ir is None or is_ is None or it is None:
            return None
        i_prom = (ir + is_ + it) / 3.0
        if i_prom <= 0.0 or i_prom < umbral_corriente_minima:
            return None
        desv_max = max(abs(ir - i_prom), abs(is_ - i_prom), abs(it - i_prom))
        return round((desv_max / i_prom) * 100.0, 2)

    @staticmethod
    def determinar_estado_fp(
        fp: float | None,
        umbral_penalidad: float = 0.95,
        umbral_objetivo: float = 0.96,
    ) -> EstadoFactorPotencia:
        """Determina el estado normativo del Factor de Potencia según Res. ENRE/Distribuidoras.

        Sin factor de potencia medido el estado es SIN_DATOS: afirmar OPTIMO sobre un
        valor inexistente hacía que la UI mostrara un badge «ÓPTIMO» junto a un guion.
        """
        if fp is None:
            return EstadoFactorPotencia.SIN_DATOS
        if fp >= umbral_objetivo:
            return EstadoFactorPotencia.OPTIMO
        if fp >= umbral_penalidad:
            return EstadoFactorPotencia.ADVERTENCIA
        return EstadoFactorPotencia.PENALIZADO

    @staticmethod
    def determinar_estado_tension(
        vr: float | None,
        vs: float | None,
        vt: float | None,
        umbral_baja: float = 198.0,
        umbral_alta: float = 242.0,
    ) -> EstadoTension:
        """Determina el estado normativo de tensión según banda contractual ENRE (220V ±10%).

        Sin ninguna tensión medida el estado es SIN_DATOS: un medidor caído no está
        reportando "tensión normal".
        """
        tensiones = [v for v in (vr, vs, vt) if v is not None]
        if not tensiones:
            return EstadoTension.SIN_DATOS

        if any(v < umbral_baja for v in tensiones):
            return EstadoTension.SUBTENSION
        if any(v > umbral_alta for v in tensiones):
            return EstadoTension.SOBRETENSION
        return EstadoTension.NORMAL

    @classmethod
    def calcular_analitica_completa(
        cls,
        lectura: LecturaInstantanea,
        fp_objetivo: float = 0.96,
    ) -> AnaliticaCalidadEnergia:
        """Calcula el bloque analítico completo de calidad de energía y compensación de reactiva."""
        # 1. Potencia activa total en kW
        p_activa_w: float | None = None
        if lectura.potencia_activa_total is not None:
            p_activa_w = lectura.potencia_activa_total.vatios
        else:
            p_vals = [
                f.potencia_activa.vatios
                for f in (lectura.fase_r, lectura.fase_s, lectura.fase_t)
                if f.potencia_activa is not None
            ]
            if p_vals:
                p_activa_w = sum(p_vals)

        p_activa_kw = (p_activa_w / 1000.0) if p_activa_w is not None else None

        # 2. Factor de potencia total
        fp_val: float | None = None
        if lectura.factor_potencia_total is not None:
            fp_val = lectura.factor_potencia_total.valor
        else:
            fp_vals = [
                f.factor_potencia.valor
                for f in (lectura.fase_r, lectura.fase_s, lectura.fase_t)
                if f.factor_potencia is not None
            ]
            if fp_vals:
                fp_val = sum(fp_vals) / len(fp_vals)

        # 3. Dimensionamiento reactiva y penalización
        requiere_comp = False
        qc_kvar: float | None = None
        banco_sug: float | None = None
        penalizacion_ars: float | None = None

        if p_activa_kw is not None and p_activa_kw > 0.0 and fp_val is not None and fp_val > 0.0:
            qc_calc = DimensionadorCompensacionService.calcular_potencia_compensacion(
                p_activa_kw, fp_val, fp_objetivo=fp_objetivo
            )
            if qc_calc is not None and qc_calc > 0.0:
                requiere_comp = True
                qc_kvar = qc_calc
                banco_sug = DimensionadorCompensacionService.sugerir_banco_comercial(qc_kvar)
            else:
                qc_kvar = 0.0
                requiere_comp = False

            penalizacion_ars = DimensionadorCompensacionService.estimar_penalizacion_mensual_ars(p_activa_kw, fp_val)

        # 4. Desbalances
        vr = lectura.fase_r.tension.voltios if lectura.fase_r.tension else None
        vs = lectura.fase_s.tension.voltios if lectura.fase_s.tension else None
        vt = lectura.fase_t.tension.voltios if lectura.fase_t.tension else None

        vur = lectura.desbalance_tension_porcentaje
        if vur is None:
            vur = cls.calcular_desbalance_tension(vr, vs, vt)

        ir = lectura.fase_r.corriente.amperios if lectura.fase_r.corriente else None
        is_ = lectura.fase_s.corriente.amperios if lectura.fase_s.corriente else None
        it = lectura.fase_t.corriente.amperios if lectura.fase_t.corriente else None
        iur = cls.calcular_desbalance_corriente(ir, is_, it)

        # 5. Estados normativos
        estado_fp = cls.determinar_estado_fp(fp_val, umbral_penalidad=0.95, umbral_objetivo=fp_objetivo)
        estado_tension = cls.determinar_estado_tension(vr, vs, vt)

        return AnaliticaCalidadEnergia(
            requiere_compensacion=requiere_comp,
            potencia_reactiva_a_compensar_kvar=qc_kvar,
            banco_sugerido_kvar=banco_sug,
            penalizacion_estimada_ars=penalizacion_ars,
            desbalance_tension_porcentaje=vur,
            desbalance_corriente_porcentaje=iur,
            estado_fp=estado_fp,
            estado_tension=estado_tension,
        )


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
