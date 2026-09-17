"""Servicio de dominio para evaluar el diagnóstico metrológico y de instalación física."""

from __future__ import annotations

from src.domain.telemetria.entities import LecturaInstantanea
from src.domain.telemetria.servicios.evaluador_anomalias_fases import EvaluadorAnomaliasFasesService
from src.domain.telemetria.servicios.evaluador_ti_desconectado import EvaluadorTiDesconectadoService
from src.domain.telemetria.servicios.evaluador_tis_misma_fase import EvaluadorTisMismaFaseService
from src.domain.telemetria.value_objects import DiagnosticoInstalacion, EstadoMetrologicoLectura


class EvaluadorDiagnosticoInstalacionService:
    """Consolida el estado metrológico de la instalación a partir de anomalías de TIs."""

    @staticmethod
    def _determinar_fase_duplicada_subordinada(fase_a: str, fase_b: str, lectura: LecturaInstantanea) -> str:
        fases_map = {"R": lectura.fase_r, "S": lectura.fase_s, "T": lectura.fase_t}
        med_a = fases_map.get(fase_a)
        med_b = fases_map.get(fase_b)
        fp_a = abs(med_a.factor_potencia.valor) if med_a and med_a.factor_potencia else 0.0
        fp_b = abs(med_b.factor_potencia.valor) if med_b and med_b.factor_potencia else 0.0
        return fase_a if fp_a < fp_b else fase_b

    @classmethod
    def _identificar_comprometidas_y_anomalias(
        cls,
        dispositivo_id: str,
        lectura: LecturaInstantanea,
        fases_con_ti: list[str] | set[str] | None,
    ) -> tuple[set[str], list[str], list[str]]:
        comprometidas: set[str] = set()
        anomalias: list[str] = []
        acciones: list[str] = []

        alertas_mf = EvaluadorTisMismaFaseService.evaluar_alerta_tis_en_misma_fase(
            dispositivo_id=dispositivo_id, lectura=lectura, fases_con_ti=fases_con_ti
        )
        for a in alertas_mf:
            anomalias.append(f"TIS_EN_MISMA_FASE: {a.mensaje}")
            if a.fase and "-" in a.fase:
                partes = a.fase.split("-")
                dup, base = partes[0], partes[1]
                comprometidas.add(dup)
                acciones.append(
                    f"Reubicar sensor toroidal del canal {dup} que abraza conductor de Fase {base} hacia Fase {dup} física."
                )
            elif a.fase and "R" in a.fase and "S" in a.fase:
                dup = cls._determinar_fase_duplicada_subordinada("R", "S", lectura)
                comprometidas.add(dup)
                base = "S" if dup == "R" else "R"
                acciones.append(
                    f"Reubicar sensor toroidal del canal {dup} que abraza conductor de Fase {base} hacia Fase {dup} física."
                )

        alertas_desc = EvaluadorTiDesconectadoService.evaluar_alerta_ti_desconectado(
            dispositivo_id=dispositivo_id, lectura=lectura, fases_con_ti=fases_con_ti
        )
        for a in alertas_desc:
            anomalias.append(f"TI_DESCONECTADO: {a.mensaje}")
            if a.fase:
                comprometidas.add(a.fase)
                acciones.append(f"Conectar circuito secundario del sensor toroidal en canal de Fase {a.fase}.")

        alertas_cruce = EvaluadorAnomaliasFasesService.evaluar_alerta_cruce_ti(
            dispositivo_id=dispositivo_id, lectura=lectura, fases_con_ti=fases_con_ti
        )
        for a in alertas_cruce:
            anomalias.append(f"CRUCE_TI_FASE: {a.mensaje}")
            if a.fase:
                comprometidas.add(a.fase)
                acciones.append(f"Corregir cruce de bornes en canal de Fase {a.fase}.")

        return comprometidas, anomalias, acciones

    @staticmethod
    def _estimar_potencia_simetrica(fases_validas: list[str], lectura: LecturaInstantanea) -> float | None:
        if len(fases_validas) != 1:
            return None
        fases_map = {"R": lectura.fase_r, "S": lectura.fase_s, "T": lectura.fase_t}
        med = fases_map.get(fases_validas[0])
        if med and med.potencia_activa and med.potencia_activa.vatios > 500.0:
            return round(3.0 * med.potencia_activa.vatios, 1)
        return None

    @classmethod
    def evaluar_diagnostico(
        cls,
        lectura: LecturaInstantanea,
        fases_con_ti: list[str] | set[str] | None = None,
        dispositivo_id: str = "",
    ) -> DiagnosticoInstalacion:
        """Determina el estado metrológico integral y acciones correctivas para la lectura."""
        fases_esperadas = [f.strip().upper() for f in fases_con_ti] if fases_con_ti is not None else ["R", "S", "T"]

        comprometidas, anomalias, acciones = cls._identificar_comprometidas_y_anomalias(
            dispositivo_id, lectura, fases_con_ti
        )

        validas = [f for f in fases_esperadas if f not in comprometidas]
        if not anomalias:
            estado = EstadoMetrologicoLectura.CONFIABLE
        elif not validas:
            estado = EstadoMetrologicoLectura.NO_CONFIABLE
        else:
            estado = EstadoMetrologicoLectura.DEGRADADO

        p_estimada = cls._estimar_potencia_simetrica(validas, lectura)
        accion_final = " ".join(acciones) if acciones else None

        return DiagnosticoInstalacion(
            estado_metrologico=estado,
            fases_validas=tuple(validas),
            fases_comprometidas=tuple(sorted(comprometidas)),
            anomalias_detectadas=tuple(anomalias),
            potencia_estimada_simetrica_w=p_estimada,
            accion_correctiva_sugerida=accion_final,
        )
