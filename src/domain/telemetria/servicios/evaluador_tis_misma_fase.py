from __future__ import annotations

from datetime import datetime, timezone

from src.domain.telemetria.entities import AlertaDispositivo, LecturaInstantanea, MedicionFase
from src.domain.telemetria.value_objects import SeveridadAlerta


class EvaluadorTisMismaFaseService:
    """Servicio de dominio para detectar TIs conectados a la misma fase física."""

    @staticmethod
    def _evaluar_par(
        dispositivo_id: str,
        fa: str,
        fb: str,
        med_a: MedicionFase,
        med_b: MedicionFase,
        t_disparo: datetime,
        umbral_corriente_minima: float,
        umbral_delta_corriente_max: float,
        umbral_fp_normal: float,
        umbral_fp_desfasado: float,
    ) -> AlertaDispositivo | None:
        ia = med_a.corriente.amperios if med_a.corriente else 0.0
        ib = med_b.corriente.amperios if med_b.corriente else 0.0

        if ia < umbral_corriente_minima or ib < umbral_corriente_minima:
            return None

        denom = max(ia, ib)
        if denom <= 0.0 or (abs(ia - ib) / denom) > umbral_delta_corriente_max:
            return None

        fp_a_obj = med_a.factor_potencia
        fp_b_obj = med_b.factor_potencia
        if fp_a_obj is None or fp_b_obj is None:
            return None

        fp_a, fp_b = abs(fp_a_obj.valor), abs(fp_b_obj.valor)
        es_a_norm = (fp_a >= umbral_fp_normal) and (fp_b <= umbral_fp_desfasado)
        es_b_norm = (fp_b >= umbral_fp_normal) and (fp_a <= umbral_fp_desfasado)

        if not (es_a_norm or es_b_norm):
            return None

        fase_real = fa if es_a_norm else fb
        fase_desf = fb if es_a_norm else fa
        fp_real = fp_a_obj.valor if es_a_norm else fp_b_obj.valor
        fp_desf = fp_b_obj.valor if es_a_norm else fp_a_obj.valor
        delta_rel = abs(ia - ib) / denom

        return AlertaDispositivo(
            id=None,
            dispositivo_id=dispositivo_id,
            tipo_alerta="TIS_EN_MISMA_FASE",
            severidad=SeveridadAlerta.CRITICAL,
            mensaje=(
                f"Ambos Transformadores de Corriente (Canal {fa} y Canal {fb}) están midiendo la misma fase física. "
                f"Corrientes idénticas (I{fa}={ia:.1f}A vs I{fb}={ib:.1f}A, Δ={delta_rel * 100:.1f}%) "
                f"con desfasaje angular severo (FP {fase_real}={fp_real:.2f} vs FP {fase_desf}={fp_desf:.2f})."
            ),
            disparada_en=t_disparo,
            fase=f"{fase_desf}-{fase_real}",
            valor_medido=delta_rel * 100.0,
            valor_umbral=umbral_delta_corriente_max * 100.0,
            unidad="%",
            categoria="INSTALACION",
            observaciones="Corregir conexionado en campo: desconectar o reubicar el TI secundario a su conductor correspondiente.",
        )

    @classmethod
    def evaluar_alerta_tis_en_misma_fase(
        cls,
        dispositivo_id: str,
        lectura: LecturaInstantanea,
        tipo_instalacion: str = "CONSUMO",
        fases_con_ti: list[str] | set[str] | None = None,
        umbral_corriente_minima: float = 10.0,
        umbral_delta_corriente_max: float = 0.03,
        umbral_fp_normal: float = 0.70,
        umbral_fp_desfasado: float = 0.15,
    ) -> list[AlertaDispositivo]:
        """Detecta TIs conectados a la misma fase fisica (Duplicacion de TI)."""
        if tipo_instalacion == "GENERACION_FV":
            return []

        fases_activas = set(fases_con_ti) if fases_con_ti is not None else {"R", "S", "T"}
        if len(fases_activas) < 2:
            return []

        alertas: list[AlertaDispositivo] = []
        t_disparo = (
            lectura.registrado_en if (lectura and lectura.registrado_en is not None) else datetime.now(timezone.utc)
        )
        fases_dict = {"R": lectura.fase_r, "S": lectura.fase_s, "T": lectura.fase_t}

        for fa, fb in [("R", "S"), ("S", "T"), ("R", "T")]:
            if fa not in fases_activas or fb not in fases_activas:
                continue
            alerta = cls._evaluar_par(
                dispositivo_id,
                fa,
                fb,
                fases_dict[fa],
                fases_dict[fb],
                t_disparo,
                umbral_corriente_minima,
                umbral_delta_corriente_max,
                umbral_fp_normal,
                umbral_fp_desfasado,
            )
            if alerta:
                alertas.append(alerta)

        return alertas
