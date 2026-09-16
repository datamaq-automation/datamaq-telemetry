"""Servicio de dominio para evaluar la alerta de TI desconectado en fases."""

from __future__ import annotations

from datetime import datetime, timezone

from src.domain.telemetria.entities import AlertaDispositivo, LecturaInstantanea, SeveridadAlerta


class EvaluadorTiDesconectadoService:
    """Evaluador específico para la detección de transformadores de corriente no conectados."""

    @classmethod
    def evaluar_alerta_ti_desconectado(
        cls,
        dispositivo_id: str,
        lectura: LecturaInstantanea,
        fases_con_ti: list[str] | set[str] | None = None,
        umbral_tension_minima: float = 180.0,
        umbral_corriente_nula: float = 0.5,
        umbral_corriente_activa_otras: float = 10.0,
    ) -> list[AlertaDispositivo]:
        """Detecta TIs no conectados o en circuito abierto en fases con tension nominal.

        Se dispara cuando una fase con TI esperado registra tension presente (>180V)
        y corriente nula (<=0.5A), mientras otra fase registra corriente activa significativa (>=10A).
        """
        if fases_con_ti is None:
            fases_activas = {"R", "S", "T"}
        else:
            fases_activas = {f.strip().upper() for f in fases_con_ti}

        fases_map = {
            "R": lectura.fase_r,
            "S": lectura.fase_s,
            "T": lectura.fase_t,
        }

        corrientes_activas = []
        for nombre, med in fases_map.items():
            if nombre in fases_activas and med.corriente and med.corriente.amperios is not None:
                corrientes_activas.append(med.corriente.amperios)

        if not corrientes_activas:
            return []

        i_max = max(corrientes_activas)
        if i_max < umbral_corriente_activa_otras:
            return []

        t_disparo = (
            lectura.registrado_en if (lectura and lectura.registrado_en is not None) else datetime.now(timezone.utc)
        )
        alertas: list[AlertaDispositivo] = []

        for nombre, med in fases_map.items():
            if nombre not in fases_activas:
                continue

            v = med.tension.voltios if med.tension else None
            i = med.corriente.amperios if med.corriente else 0.0

            if v is not None and v >= umbral_tension_minima and i <= umbral_corriente_nula:
                alertas.append(
                    AlertaDispositivo(
                        id=None,
                        dispositivo_id=dispositivo_id,
                        tipo_alerta="TI_DESCONECTADO",
                        severidad=SeveridadAlerta.CRITICAL,
                        mensaje=(
                            f"Posible Transformador de Corriente (TI) desconectado en Fase {nombre}: "
                            f"Tensión nominal presente ({v:.1f} V) pero corriente nula ({i:.1f} A) "
                            f"mientras otras fases registran carga ({i_max:.1f} A). "
                            f"Circuito secundario abierto o TI no abrazando el conductor."
                        ),
                        disparada_en=t_disparo,
                        fase=nombre,
                        valor_medido=round(i, 2),
                        valor_umbral=umbral_corriente_nula,
                        unidad="A",
                        categoria="INSTALACION",
                        observaciones=f"Verificar cableado de bornera y conexión del núcleo toroidal en Fase {nombre}.",
                    )
                )

        return alertas
