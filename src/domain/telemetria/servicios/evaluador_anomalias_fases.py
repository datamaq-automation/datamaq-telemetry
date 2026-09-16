"""src/domain/telemetria/servicios/evaluador_anomalias_fases.py — Evaluador de anomalias de red y fases (cruce de TIs, secuencia inversa, desbalance y sobrecompensacion)."""

from datetime import datetime, timezone

from src.domain.telemetria.entities import AlertaDispositivo, LecturaInstantanea
from src.domain.telemetria.servicios.analizador_calidad_metrologica import (
    AnalizadorMetrologicoService,
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
        """Detecta cruce de TIs entre fases (CT Mismatch).

        Ocurre cuando el sensor toroidal colocado en un conductor se conecta
        en la bornera de otra fase en el medidor, provocando un desfase
        espacial inherente de 120 grados y un factor de potencia anormalmente bajo.
        """
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
            if fp_obj is None:
                continue

            fp_val = abs(fp_obj.valor)

            if i_val >= umbral_corriente_minima and fp_val <= umbral_fp_anormal:
                promedio_otras = cls._promedio_fp_otras_fases(fases_dict, nombre_fase, fases_activas)
                if promedio_otras is not None and promedio_otras >= umbral_fp_otras_normal:
                    alertas.append(
                        AlertaDispositivo(
                            id=None,
                            dispositivo_id=dispositivo_id,
                            tipo_alerta="CRUCE_TI_FASE",
                            severidad=SeveridadAlerta.WARNING,
                            mensaje=(
                                f"Posible cruce de Transformador de Corriente (TI) en Fase {nombre_fase}: "
                                f"FP={fp_obj.valor:.2f} anormalmente bajo con I={i_val:.1f}A "
                                f"mientras las otras fases registran FP promedio={promedio_otras:.2f}."
                            ),
                            disparada_en=t_disparo,
                            fase=nombre_fase,
                            valor_medido=fp_obj.valor,
                            valor_umbral=umbral_fp_anormal,
                            unidad="",
                            categoria="INSTALACION",
                            observaciones="Verificar que el canal de corriente y tension correspondan a la misma fase fisica.",
                        )
                    )

        return alertas

    evaluar_alerta_tis_en_misma_fase = EvaluadorTisMismaFaseService.evaluar_alerta_tis_en_misma_fase
    evaluar_alerta_ti_desconectado = EvaluadorTiDesconectadoService.evaluar_alerta_ti_desconectado

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

        if desbalance >= umbral_critico:
            return AlertaDispositivo(
                id=None,
                dispositivo_id=dispositivo_id,
                tipo_alerta="DESBALANCE_CORRIENTE_CRITICAL",
                severidad=SeveridadAlerta.CRITICAL,
                mensaje=(
                    f"Desbalance critico de corriente entre fases: {desbalance:.1f}% "
                    f"(Maximo critico: {umbral_critico:.1f}%). Riesgo de sobrecalentamiento del conductor neutro."
                ),
                disparada_en=t_disparo,
                fase="TOTAL",
                valor_medido=round(desbalance, 2),
                valor_umbral=umbral_critico,
                unidad="%",
                categoria="DESBALANCE_CORRIENTE",
                observaciones="Desbalance severo. Redistribuir cargas monofasicas entre las tres fases.",
            )
        elif desbalance >= umbral_warning:
            return AlertaDispositivo(
                id=None,
                dispositivo_id=dispositivo_id,
                tipo_alerta="DESBALANCE_CORRIENTE",
                severidad=SeveridadAlerta.WARNING,
                mensaje=(
                    f"Desbalance de corriente elevado: {desbalance:.1f}% (Limite advertencia: {umbral_warning:.1f}%)."
                ),
                disparada_en=t_disparo,
                fase="TOTAL",
                valor_medido=round(desbalance, 2),
                valor_umbral=umbral_warning,
                unidad="%",
                categoria="DESBALANCE_CORRIENTE",
                observaciones="Carga asimetrica entre fases. Evaluar balanceo de lineas.",
            )

        return None

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
