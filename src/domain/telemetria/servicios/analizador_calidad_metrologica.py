import cmath
import math
from datetime import datetime, timezone

from src.domain.telemetria.analizador_reactiva import DimensionadorCompensacionService
from src.domain.telemetria.entities import LecturaInstantanea, MedicionFase
from src.domain.telemetria.servicios.calculos_potencia import CalculadoraPotenciaService
from src.domain.telemetria.value_objects import (
    AnaliticaCalidadEnergia,
    Corriente,
    EstadoFactorPotencia,
    EstadoTension,
    FactorPotencia,
    PotenciaActiva,
    PotenciaAparente,
    PotenciaReactiva,
    Tension,
)


class AnalizadorMetrologicoService:
    """Servicio de dominio puro para validar balances y analítica metrológica de red."""

    @staticmethod
    def es_instalacion_monofasica(tipo_instalacion: str | None, fases_con_ti: str | None) -> bool:
        """Determina si una instalación es monofásica (1P2W).

        Criterio: tipo de instalación explícito ``1P2W``, o bien una única fase con TI.
        Una instalación Aron (dos fases con TI) sigue siendo trifásica a efectos de
        balance, aunque no mida la tercera corriente.
        """
        tipo_norm = (tipo_instalacion or "").strip().upper()
        if tipo_norm == "1P2W":
            return True
        return len(AnalizadorMetrologicoService.fases_con_ti_como_lista(fases_con_ti)) == 1

    @staticmethod
    def fases_con_ti_como_lista(fases_con_ti: str | list[str] | set[str] | tuple[str, ...] | None) -> set[str]:
        """Normaliza la configuración de fases con TI a un conjunto de fases en mayúsculas.

        ``None`` o vacío se interpreta como las tres fases (configuración por defecto).
        """
        if fases_con_ti is None:
            return {"R", "S", "T"}
        if isinstance(fases_con_ti, (list, set, tuple)):
            fases = {str(f).strip().upper() for f in fases_con_ti if str(f).strip()}
        else:
            fases = {f.strip().upper() for f in str(fases_con_ti).split(",") if f.strip()}
        if not fases:
            return {"R", "S", "T"}
        return fases

    @staticmethod
    def sanear_fase_sin_ti(fase: MedicionFase) -> MedicionFase:
        """Anula corriente/P/Q/S/FP/THD_I de una fase sin TI, conservando tensión y THD_V.

        En una instalación monofásica los tres bornes de tensión están en paralelo, así
        que la tensión (y su THD) es real, pero la corriente y las potencias medidas sin
        transformador de corriente son ruido que no debe propagarse.
        """
        return MedicionFase(
            tension=fase.tension,
            thd_v_porcentaje=fase.thd_v_porcentaje,
            thd_v_pct=fase.thd_v_pct,
        )

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

        th_vr = 0.0
        th_vs = -2.0 * math.pi / 3.0  # -120°
        th_vt = 2.0 * math.pi / 3.0  # +120°

        def _calc_phi(p: float | None, q: float | None) -> float:
            if p is None or q is None:
                return 0.0
            if p == 0.0 and q == 0.0:
                return 0.0
            return math.atan2(q, p)

        phi_r = _calc_phi(pr, qr)
        phi_s = _calc_phi(ps, qs)
        phi_t = _calc_phi(pt, qt)

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

        th_vr = 0.0
        th_vs = -2.0 * math.pi / 3.0  # -120°
        th_vt = 2.0 * math.pi / 3.0  # +120°

        v_r = cmath.rect(vr, th_vr)
        v_s = cmath.rect(vs, th_vs)
        v_t = cmath.rect(vt, th_vt)

        v_n = -(v_r + v_s + v_t) / 3.0
        vn_rms = round(abs(v_n), 2)
        return vn_rms

    @classmethod
    def _agregar_grupo_lecturas(
        cls,
        items: list[LecturaInstantanea],
        bucket_dt: datetime,
        es_monofasico: bool = False,
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
            s = CalculadoraPotenciaService.calcular_potencia_aparente(v, i)
            if s is None:
                s = _avg([f.potencia_aparente.va for f in fases if f.potencia_aparente])
            fp = CalculadoraPotenciaService.calcular_factor_potencia(p, s)
            if fp is None:
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

        s_tot = CalculadoraPotenciaService.calcular_potencia_aparente_total(
            *(f.potencia_aparente.va if f.potencia_aparente else None for f in (fase_r, fase_s, fase_t))
        )
        if s_tot is None:
            s_tot = _avg([it.potencia_aparente_total.va for it in items if it.potencia_aparente_total])

        fp_tot = CalculadoraPotenciaService.calcular_factor_potencia(p_tot, s_tot)
        if fp_tot is None:
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

        if es_monofasico:
            desbalance_v = None
            voltage_linea_V = None
            i_neutro = None
            v_neutro = None

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
        es_monofasico: bool = False,
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
            agregada = cls._agregar_grupo_lecturas(bucket_items, bucket_dt, es_monofasico=es_monofasico)
            resultado.append(agregada)

        return resultado

    @staticmethod
    def calcular_desbalance_corriente(
        ir: float | None,
        is_: float | None,
        it: float | None,
        umbral_corriente_minima: float = 5.0,
    ) -> float | None:
        """Calcula el Desbalance de Corriente Trifásico (IUR) según IEC 61000-4-30 / NEMA."""
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
        """Determina el estado normativo del Factor de Potencia según Res. ENRE/Distribuidoras."""
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
        """Determina el estado normativo de tensión según banda contractual ENRE (220V ±10%)."""
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
        potencia_minima_w: float = 500.0,
    ) -> AnaliticaCalidadEnergia:
        """Calcula el bloque analítico completo de calidad de energía y compensación de reactiva."""
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

        requiere_comp = False
        qc_kvar: float | None = None
        banco_sug: float | None = None
        penalizacion_ars: float | None = None

        supera_minimo = p_activa_w is not None and p_activa_w >= potencia_minima_w
        if supera_minimo and p_activa_kw is not None and fp_val is not None and fp_val > 0.0:
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
