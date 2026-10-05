"""src/domain/telemetria/servicios/evaluador_anomalias_fases.py — Evaluador de anomalias de red y fases (cruce de TIs, secuencia inversa, desbalance y sobrecompensacion)."""

from datetime import datetime, timezone

from src.domain.telemetria.entities import AlertaDispositivo, LecturaInstantanea
from src.domain.telemetria.servicios.analizador_calidad_metrologica import (
    AnalizadorMetrologicoService,
)
from src.domain.telemetria.servicios.evaluador_potencia_negativa import (
    EvaluadorPotenciaNegativaService,
)
from src.domain.telemetria.servicios.evaluador_ti_desconectado import (
    EvaluadorTiDesconectadoService,
)
from src.domain.telemetria.servicios.evaluador_tis_misma_fase import (
    EvaluadorTisMismaFaseService,
)
from src.domain.telemetria.value_objects import SeveridadAlerta


class EvaluadorAnomaliasFasesService:
    """Servicio de dominio para detectar anomalias complejas en la conexion de fases y TIs."""

    @staticmethod
    def _promedio_fp_otras_fases(fases_dict: dict, nombre_fase: str, fases_activas: set[str]) -> float | None:
        otras = [
            abs(fases_dict[f].factor_potencia.valor)
            for f in ("R", "S", "T")
            if f != nombre_fase and f in fases_activas and fases_dict[f].factor_potencia is not None
        ]
        return (sum(otras) / len(otras)) if otras else None

    @classmethod
    def evaluar_alerta_cruce_ti(
        cls,
        dispositivo_id: str,
        lectura: LecturaInstantanea,
        tipo_instalacion: str = "CONSUMO",
        fases_con_ti: list[str] | set[str] | None = None,
        umbral_corriente_minima: float = 10.0,
        umbral_fp_anormal: float = 0.40,
        umbral_fp_otras_normal: float = 0.85,
    ) -> list[AlertaDispositivo]:
        """Detecta cruce de TIs entre fases (CT Mismatch / 120° o cruce simétrico de 60°)."""
        if tipo_instalacion == "GENERACION_FV":
            return []

        fases_activas = set(fases_con_ti) if fases_con_ti is not None else {"R", "S", "T"}
        if len(fases_activas) < 2:
            return []

        alertas: list[AlertaDispositivo] = []
        t_disparo = (
            lectura.registrado_en if (lectura and lectura.registrado_en is not None) else datetime.now(timezone.utc)
        )

        fases_dict = {
            "R": lectura.fase_r,
            "S": lectura.fase_s,
            "T": lectura.fase_t,
        }

        for nombre_fase in ("R", "S", "T"):
            if nombre_fase not in fases_activas:
                continue

            med = fases_dict[nombre_fase]
            i_val = med.corriente.amperios if med.corriente else 0.0
            fp_obj = med.factor_potencia
            if fp_obj is None or i_val < umbral_corriente_minima or abs(fp_obj.valor) > umbral_fp_anormal:
                continue

            promedio_otras = cls._promedio_fp_otras_fases(fases_dict, nombre_fase, fases_activas)
            if promedio_otras is not None and promedio_otras >= umbral_fp_otras_normal:
                alertas.append(
                    cls._crear_alerta_cruce_ti(
                        dispositivo_id=dispositivo_id,
                        fase=nombre_fase,
                        fp_valor=fp_obj.valor,
                        i_val=i_val,
                        promedio_otras=promedio_otras,
                        t_disparo=t_disparo,
                        umbral_fp_anormal=umbral_fp_anormal,
                    )
                )

        alerta_60 = cls._evaluar_cruce_simetrico_60(
            dispositivo_id=dispositivo_id,
            fases_dict=fases_dict,
            fases_activas=fases_activas,
            t_disparo=t_disparo,
            umbral_corriente_minima=umbral_corriente_minima,
        )
        if alerta_60 and not alertas:
            alertas.append(alerta_60)

        return alertas

    @staticmethod
    def _evaluar_cruce_simetrico_60(
        dispositivo_id: str,
        fases_dict: dict,
        fases_activas: set[str],
        t_disparo: datetime,
        umbral_corriente_minima: float,
    ) -> AlertaDispositivo | None:
        fases_p = [f for f in ("R", "S", "T") if f in fases_activas and fases_dict[f].factor_potencia is not None]
        if len(fases_p) != 2:
            return None

        f1, f2 = fases_p[0], fases_p[1]
        m1, m2 = fases_dict[f1], fases_dict[f2]
        fp1 = abs(m1.factor_potencia.valor) if m1.factor_potencia else 1.0
        fp2 = abs(m2.factor_potencia.valor) if m2.factor_potencia else 1.0
        i1 = m1.corriente.amperios if m1.corriente else 0.0
        i2 = m2.corriente.amperios if m2.corriente else 0.0
        q1 = m1.potencia_reactiva.var if m1.potencia_reactiva else 0.0
        q2 = m2.potencia_reactiva.var if m2.potencia_reactiva else 0.0

        if i1 < umbral_corriente_minima or i2 < umbral_corriente_minima:
            return None

        if fp1 <= 0.55 and fp2 <= 0.55 and (q1 * q2 < 0):
            rel_q = abs(q1) / max(abs(q2), 1.0)
            if 0.5 <= rel_q <= 2.0:
                return AlertaDispositivo(
                    id=None,
                    dispositivo_id=dispositivo_id,
                    tipo_alerta="CRUCE_TI_FASE",
                    severidad=SeveridadAlerta.WARNING,
                    mensaje=(
                        f"Desfasaje fasorial cruzado de 60° detectado entre Fase {f1} y Fase {f2}: "
                        f"FP_{f1}={fp1:.2f}, FP_{f2}={fp2:.2f} con potencias reactivas opuestas compensadas."
                    ),
                    disparada_en=t_disparo,
                    fase=f"{f1}-{f2}",
                    valor_medido=min(fp1, fp2),
                    valor_umbral=0.55,
                    unidad="",
                    categoria="INSTALACION",
                    observaciones="Verificar secuencia y conexión de bornes de tensión o rotar canales de TI.",
                )
        return None

    @staticmethod
    def _crear_alerta_cruce_ti(
        dispositivo_id: str,
        fase: str,
        fp_valor: float,
        i_val: float,
        promedio_otras: float,
        t_disparo: datetime,
        umbral_fp_anormal: float,
    ) -> AlertaDispositivo:
        return AlertaDispositivo(
            id=None,
            dispositivo_id=dispositivo_id,
            tipo_alerta="CRUCE_TI_FASE",
            severidad=SeveridadAlerta.WARNING,
            mensaje=(
                f"Posible cruce de Transformador de Corriente (TI) en Fase {fase}: "
                f"FP={fp_valor:.2f} anormalmente bajo con I={i_val:.1f}A "
                f"mientras las otras fases registran FP promedio={promedio_otras:.2f}."
            ),
            disparada_en=t_disparo,
            fase=fase,
            valor_medido=fp_valor,
            valor_umbral=umbral_fp_anormal,
            unidad="",
            categoria="INSTALACION",
            observaciones="Verificar que el canal de corriente y tension correspondan a la misma fase fisica.",
        )

    evaluar_alerta_tis_en_misma_fase = EvaluadorTisMismaFaseService.evaluar_alerta_tis_en_misma_fase
    evaluar_alerta_ti_desconectado = EvaluadorTiDesconectadoService.evaluar_alerta_ti_desconectado
    evaluar_alerta_potencia_negativa = EvaluadorPotenciaNegativaService.evaluar_alerta_potencia_negativa

    @staticmethod
    def evaluar_alerta_desbalance_corriente(
        dispositivo_id: str,
        lectura: LecturaInstantanea,
        es_monofasico: bool = False,
        umbral_warning: float = 15.0,
        umbral_critico: float = 25.0,
        umbral_corriente_minima: float = 5.0,
    ) -> AlertaDispositivo | None:
        """Evalua desbalance de corriente entre fases segun IEEE Std 141 / NEMA."""
        if es_monofasico:
            return None

        ir = lectura.fase_r.corriente.amperios if lectura.fase_r.corriente else None
        is_ = lectura.fase_s.corriente.amperios if lectura.fase_s.corriente else None
        it = lectura.fase_t.corriente.amperios if lectura.fase_t.corriente else None

        desbalance = AnalizadorMetrologicoService.calcular_desbalance_corriente(
            ir, is_, it, umbral_corriente_minima=umbral_corriente_minima
        )
        if desbalance is None:
            return None

        t_disparo = (
            lectura.registrado_en if (lectura and lectura.registrado_en is not None) else datetime.now(timezone.utc)
        )

        es_critico = desbalance >= umbral_critico
        es_warning = desbalance >= umbral_warning
        if not (es_critico or es_warning):
            return None

        tipo = "DESBALANCE_CORRIENTE_CRITICAL" if es_critico else "DESBALANCE_CORRIENTE"
        sev = SeveridadAlerta.CRITICAL if es_critico else SeveridadAlerta.WARNING
        umbral = umbral_critico if es_critico else umbral_warning
        msg = (
            f"Desbalance critico de corriente entre fases: {desbalance:.1f}% (Maximo critico: {umbral_critico:.1f}%)."
            if es_critico
            else f"Desbalance de corriente elevado: {desbalance:.1f}% (Limite advertencia: {umbral_warning:.1f}%)."
        )
        obs = (
            "Desbalance severo. Redistribuir cargas monofasicas entre las tres fases."
            if es_critico
            else "Carga asimetrica entre fases. Evaluar balanceo de lineas."
        )

        return AlertaDispositivo(
            id=None,
            dispositivo_id=dispositivo_id,
            tipo_alerta=tipo,
            severidad=sev,
            mensaje=msg,
            disparada_en=t_disparo,
            fase="TOTAL",
            valor_medido=round(desbalance, 2),
            valor_umbral=umbral,
            unidad="%",
            categoria="DESBALANCE_CORRIENTE",
            observaciones=obs,
        )

    @staticmethod
    def evaluar_alerta_secuencia_fases(
        dispositivo_id: str,
        lectura: LecturaInstantanea,
        es_monofasico: bool = False,
        secuencia_reportada: str | None = None,
    ) -> AlertaDispositivo | None:
        """Evalua si el orden o secuencia de fases de la red es inversa (R-T-S).

        En maquinas asincronas trifasicas, una secuencia inversa provoca giro
        en reversa, ocasionando fallas hidraulicas y roturas mecanicas.
        """
        if es_monofasico or not secuencia_reportada:
            return None

        sec = secuencia_reportada.strip().upper()
        if sec in ("RTS", "INVERSA", "NEGATIVA", "INV"):
            t_disparo = (
                lectura.registrado_en if (lectura and lectura.registrado_en is not None) else datetime.now(timezone.utc)
            )
            return AlertaDispositivo(
                id=None,
                dispositivo_id=dispositivo_id,
                tipo_alerta="SECUENCIA_FASES_INVERSA",
                severidad=SeveridadAlerta.CRITICAL,
                mensaje=(
                    f"Secuencia de fases inversa detectada ({sec}). "
                    "Peligro de rotacion contraria y rotura mecanica en motores trifasicos."
                ),
                disparada_en=t_disparo,
                fase="3F",
                valor_medido=None,
                valor_umbral=None,
                unidad="",
                categoria="SUMINISTRO",
                observaciones="Invertir dos fases en el tablero principal de alimentacion.",
            )

        return None

    @staticmethod
    def evaluar_alerta_sobrecompensacion_reactiva(
        dispositivo_id: str,
        lectura: LecturaInstantanea,
        potencia_minima_w: float = 500.0,
        umbral_q_capacitiva_var: float = -500.0,
    ) -> AlertaDispositivo | None:
        """Evalua inyeccion excesiva de potencia reactiva capacitiva hacia la red."""
        p_obj = lectura.potencia_activa_total
        q_obj = lectura.potencia_reactiva_total
        if p_obj is None or q_obj is None:
            return None

        p_val = p_obj.vatios
        q_val = q_obj.var

        if p_val >= potencia_minima_w and q_val <= umbral_q_capacitiva_var:
            t_disparo = (
                lectura.registrado_en if (lectura and lectura.registrado_en is not None) else datetime.now(timezone.utc)
            )
            return AlertaDispositivo(
                id=None,
                dispositivo_id=dispositivo_id,
                tipo_alerta="SOBRECOMPENSACION_REACTIVA",
                severidad=SeveridadAlerta.WARNING,
                mensaje=(
                    f"Sobrecompensacion reactiva capacitiva hacia la red: Q={q_val:.1f} var "
                    f"con P={p_val:.1f} W. Riesgo de sobretension y penalizaciones."
                ),
                disparada_en=t_disparo,
                fase="TOTAL",
                valor_medido=q_val,
                valor_umbral=umbral_q_capacitiva_var,
                unidad="var",
                categoria="FACTOR_POTENCIA",
                observaciones="Banco de capacitores sobrecompensado o resonancia capacitiva. Desconectar escalones fijos.",
            )

        return None
