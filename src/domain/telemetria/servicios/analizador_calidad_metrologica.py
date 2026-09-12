"""src/domain/telemetria/servicios/analizador_calidad_metrologica.py."""

import cmath
import math
from datetime import datetime

from src.domain.telemetria.analizador_reactiva import DimensionadorCompensacionService
from src.domain.telemetria.entities import LecturaInstantanea, MedicionFase
from src.domain.telemetria.servicios.agregador_lecturas import AgregadorLecturasService
from src.domain.telemetria.value_objects import (
    AnaliticaCalidadEnergia,
    Corriente,
    EstadoFactorPotencia,
    EstadoTension,
    PotenciaActiva,
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
        """Calcula la corriente de neutro estimada (RMS) mediante suma fasorial de Kirchhoff."""
        if ir is None or is_ is None or it is None:
            return None

        th_vr, th_vs, th_vt = 0.0, -2.0 * math.pi / 3.0, 2.0 * math.pi / 3.0

        def _calc_phi(p: float | None, q: float | None) -> float:
            return math.atan2(q, p) if p and q else 0.0

        phi_r = _calc_phi(pr, qr)
        phi_s = _calc_phi(ps, qs)
        phi_t = _calc_phi(pt, qt)

        i_r = cmath.rect(ir, th_vr - phi_r)
        i_s = cmath.rect(is_, th_vs - phi_s)
        i_t = cmath.rect(it, th_vt - phi_t)

        i_n = -(i_r + i_s + i_t)
        return Corriente(amperios=round(abs(i_n), 2))

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
        """Calcula la tensión de neutro estimada (RMS) mediante suma fasorial de Kirchhoff."""
        if vr is None or vs is None or vt is None:
            return None

        th_vr, th_vs, th_vt = 0.0, -2.0 * math.pi / 3.0, 2.0 * math.pi / 3.0
        v_r = cmath.rect(vr, th_vr)
        v_s = cmath.rect(vs, th_vs)
        v_t = cmath.rect(vt, th_vt)
        return round(abs(-(v_r + v_s + v_t) / 3.0), 2)

    agregar_lecturas_en_intervalo = AgregadorLecturasService.agregar_lecturas_en_intervalo

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
    def _evaluar_abstencion_enre(cls, dispositivo: object | None) -> str | None:
        if dispositivo is None:
            return None
        tipo_inst = getattr(dispositivo, "tipo_instalacion", None)
        fases_ti = getattr(dispositivo, "fases_con_ti", None)
        es_monofasico = tipo_inst == "MONOFASICO" or (fases_ti and len(cls.fases_con_ti_como_lista(fases_ti)) == 1)
        potencia_contratada_kw = getattr(dispositivo, "potencia_contratada_kw", None)
        tarifa = getattr(dispositivo, "tarifa", None)

        if es_monofasico:
            return "Instalación monofásica exenta de penalización por reactiva (Res. ENRE 184/2000)"
        if tarifa and (tarifa.upper().startswith("T1") or "RESIDENCIAL" in tarifa.upper()):
            return "Tarifa residencial exenta de penalización por reactiva (Res. ENRE 184/2000)"
        if potencia_contratada_kw is not None and potencia_contratada_kw < 10.0:
            return "Potencia contratada menor a 10 kW exenta de penalización (Res. ENRE 184/2000)"
        return None

    @classmethod
    def _obtener_potencia_y_fp(cls, lectura: LecturaInstantanea) -> tuple[float | None, float | None, float | None]:
        p_activa_w: float | None = None
        if lectura.potencia_activa_total is not None:
            p_activa_w = lectura.potencia_activa_total.vatios
        else:
            p_vals = [
                f.potencia_activa.vatios for f in (lectura.fase_r, lectura.fase_s, lectura.fase_t) if f.potencia_activa
            ]
            p_activa_w = sum(p_vals) if p_vals else None

        p_activa_kw = (p_activa_w / 1000.0) if p_activa_w is not None else None

        fp_val: float | None = None
        if lectura.factor_potencia_total is not None:
            fp_val = lectura.factor_potencia_total.valor
        else:
            fp_vals = [
                f.factor_potencia.valor for f in (lectura.fase_r, lectura.fase_s, lectura.fase_t) if f.factor_potencia
            ]
            fp_val = (sum(fp_vals) / len(fp_vals)) if fp_vals else None

        return p_activa_w, p_activa_kw, fp_val

    @classmethod
    def _evaluar_compensacion_reactiva(
        cls,
        p_activa_w: float | None,
        p_activa_kw: float | None,
        fp_val: float | None,
        fp_objetivo: float,
        potencia_minima_w: float,
    ) -> tuple[bool, float | None, float | None, float | None, float | None]:
        supera_minimo = p_activa_w is not None and p_activa_w >= potencia_minima_w
        if not (supera_minimo and p_activa_kw is not None and fp_val is not None and fp_val > 0.0):
            return False, None, None, None, 0.0

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
            banco_sug = None

        penalizacion_ars = DimensionadorCompensacionService.estimar_penalizacion_mensual_ars(p_activa_kw, fp_val)
        recargo_pct = round(((0.95 / fp_val) - 1.0) * 100.0, 2) if fp_val < 0.95 else 0.0
        return requiere_comp, qc_kvar, banco_sug, penalizacion_ars, recargo_pct

    @classmethod
    def calcular_analitica_completa(
        cls,
        lectura: LecturaInstantanea,
        fp_objetivo: float = 0.96,
        potencia_minima_w: float = 500.0,
        dispositivo: object | None = None,
        ventana_evaluacion_min: int = 15,
        vigente_desde: datetime | None = None,
    ) -> AnaliticaCalidadEnergia:
        """Calcula el bloque analítico completo de calidad de energía y compensación de reactiva."""
        p_activa_w, p_activa_kw, fp_val = cls._obtener_potencia_y_fp(lectura)
        motivo_abstencion = cls._evaluar_abstencion_enre(dispositivo)

        if motivo_abstencion is not None:
            requiere_comp, qc_kvar, banco_sug, penalizacion_ars, recargo_pct = False, None, None, None, 0.0
        else:
            requiere_comp, qc_kvar, banco_sug, penalizacion_ars, recargo_pct = cls._evaluar_compensacion_reactiva(
                p_activa_w, p_activa_kw, fp_val, fp_objetivo, potencia_minima_w
            )

        vr = lectura.fase_r.tension.voltios if lectura.fase_r.tension else None
        vs = lectura.fase_s.tension.voltios if lectura.fase_s.tension else None
        vt = lectura.fase_t.tension.voltios if lectura.fase_t.tension else None

        vur = lectura.desbalance_tension_porcentaje or cls.calcular_desbalance_tension(vr, vs, vt)

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
            recargo_porcentaje=recargo_pct,
            motivo_abstencion=motivo_abstencion,
            ventana_evaluacion_min=ventana_evaluacion_min,
            vigente_desde=vigente_desde,
            factor_potencia_integrado=fp_val,
        )
