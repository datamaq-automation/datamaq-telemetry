"""src/domain/telemetria/servicios/evaluador_potencia_negativa.py — Detección de potencia negativa/inyección."""

from __future__ import annotations

from datetime import datetime, timezone

from src.domain.telemetria.entities import (
    AlertaDispositivo,
    LecturaInstantanea,
    SeveridadAlerta,
)


class EvaluadorPotenciaNegativaService:
    """Detección de inyección indeseada de potencia (P < 0)."""

    @staticmethod
    def evaluar_alerta_potencia_negativa(
        dispositivo_id: str,
        lectura: LecturaInstantanea,
        tipo_instalacion: str = "CONSUMO",
        umbral_p_minima_w: float = -100.0,
    ) -> AlertaDispositivo | None:
        """Detecta inyeccion indeseada de potencia (P < 0).

        En instalacion de CONSUMO, P < 0 es anomalo (medidor mide al reves,
        TI invertida, o rotacion angular mal calibrada).
        """
        if tipo_instalacion == "GENERACION_FV":
            return None

        p_obj = lectura.potencia_activa_total
        if p_obj is None:
            return None

        p_val = p_obj.vatios
        if p_val >= umbral_p_minima_w:
            return None

        t_disparo = (
            lectura.registrado_en if lectura and lectura.registrado_en is not None else datetime.now(timezone.utc)
        )

        return AlertaDispositivo(
            id=None,
            dispositivo_id=dispositivo_id,
            tipo_alerta="POTENCIA_NEGATIVA",
            severidad=SeveridadAlerta.CRITICAL,
            mensaje=(
                f"Inyeccion de potencia detectada: P={p_val:.1f} W "
                f"(< {umbral_p_minima_w:.0f} W). Verificar polaridad del TI "
                f"o rotacion angular de correccion."
            ),
            disparada_en=t_disparo,
            fase="TOTAL",
            valor_medido=p_val,
            valor_umbral=umbral_p_minima_w,
            unidad="W",
            categoria="POLARIDAD_TI",
            observaciones=(
                "Si medidor no tiene generacion, verificar: "
                "1) Polaridad de TI (P1→fuente), 2) Valor de correccion_angular_fases en YAML, "
                "3) Cableado de tension vs. TI mismo."
            ),
        )
