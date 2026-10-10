"""src/domain/telemetria/servicios/evaluador_alertas_calidad.py."""

from datetime import datetime, timezone

from src.domain.telemetria.entities import AlertaDispositivo, LecturaInstantanea
from src.domain.telemetria.servicios.analizador_calidad_metrologica import (
    AnalizadorMetrologicoService,
)
from src.domain.telemetria.servicios.evaluador_anomalias_fases import (
    EvaluadorAnomaliasFasesService,
)
from src.domain.telemetria.value_objects import SeveridadAlerta

# Los umbrales de THD_V (5 % y 8 %) son internos. La norma se cita solo como referencia, sin afirmar cumplimiento.
# Decisión: decisions/2026-10-09_alcance-thd-y-umbral-fiabilidad.md (addendum 2026-10-10).
_REFERENCIA_THD_V = "referencia: IEEE 519-2014 fija 8 % en ≤1 kV y 5 % en 1 a 69 kV en el PCC"


class EvaluadorAlertasCalidadService(EvaluadorAnomaliasFasesService):
    """Evaluación pura de reglas normativas y generación de alertas de calidad de red."""

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
            vur = AnalizadorMetrologicoService.calcular_desbalance_tension(vr, vs, vt)

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
                            mensaje=f"THD de Tensión Crítico en Fase {nombre_fase}: {thd_v}% (umbral interno: {umbral_thd_v_critico}%; {_REFERENCIA_THD_V})",
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
                            mensaje=f"THD de Tensión Elevado en Fase {nombre_fase}: {thd_v}% (umbral interno: {umbral_thd_v_warning}%; {_REFERENCIA_THD_V})",
                            disparada_en=t_disparo,
                            fase=nombre_fase,
                            valor_medido=thd_v,
                            valor_umbral=umbral_thd_v_warning,
                            unidad="%",
                            categoria="DISTORSION_ARMONICA",
                            observaciones="Supera el umbral interno. Verificar presencia de cargas no lineales o variadores de velocidad.",
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
