"""src/domain/disponibilidad/servicios/calculador_metricas_oee.py — Servicio de dominio para calcular métricas de disponibilidad y OEE."""

from datetime import datetime

from src.domain.disponibilidad.entities import EventoDisponibilidad
from src.domain.disponibilidad.value_objects import (
    EstadoMaquina,
    MetricasDisponibilidadOEE,
    TipoParada,
)


class CalculadorMetricasOEEService:
    """Calcula el factor de disponibilidad OEE y métricas MTBF/MTTR a partir de eventos."""

    @classmethod
    def calcular_metricas(
        cls,
        eventos: list[EventoDisponibilidad],
        inicio: datetime,
        fin: datetime,
    ) -> MetricasDisponibilidadOEE:
        """Calcula métricas OEE en la ventana [inicio, fin] recortando eventos."""
        tiempo_total_s = max(0.0, (fin - inicio).total_seconds())

        tiempo_marcha_s = 0.0
        tiempo_parada_prog_s = 0.0
        tiempo_parada_no_prog_s = 0.0

        cant_paradas_no_prog = 0
        cant_paradas_prog = 0
        cant_ciclos_marcha = 0

        for e in eventos:
            ev_fin_real = e.fin_at or fin
            # Intersección con la ventana [inicio, fin]
            t_inicio = max(inicio, e.inicio_at)
            t_fin = min(fin, ev_fin_real)

            if t_inicio >= t_fin:
                continue

            dur_s = (t_fin - t_inicio).total_seconds()

            if e.estado == EstadoMaquina.MARCHA:
                tiempo_marcha_s += dur_s
                cant_ciclos_marcha += 1
            elif e.estado == EstadoMaquina.PARADA:
                if e.tipo_parada == TipoParada.PROGRAMADA:
                    tiempo_parada_prog_s += dur_s
                    cant_paradas_prog += 1
                else:
                    tiempo_parada_no_prog_s += dur_s
                    cant_paradas_no_prog += 1

        tiempo_planificado_carga_s = max(0.0, tiempo_total_s - tiempo_parada_prog_s)
        if tiempo_planificado_carga_s > 0:
            disp_pct = (tiempo_marcha_s / tiempo_planificado_carga_s) * 100.0
        else:
            disp_pct = 0.0

        disp_pct = min(100.0, max(0.0, disp_pct))

        mtbf_h = tiempo_marcha_s / (3600.0 * cant_paradas_no_prog) if cant_paradas_no_prog > 0 else None
        mttr_h = tiempo_parada_no_prog_s / (3600.0 * cant_paradas_no_prog) if cant_paradas_no_prog > 0 else None

        return MetricasDisponibilidadOEE(
            periodo_inicio=inicio,
            periodo_fin=fin,
            tiempo_total_s=tiempo_total_s,
            tiempo_marcha_s=tiempo_marcha_s,
            tiempo_parada_programada_s=tiempo_parada_prog_s,
            tiempo_parada_no_programada_s=tiempo_parada_no_prog_s,
            disponibilidad_oee_pct=round(disp_pct, 3),
            mtbf_horas=round(mtbf_h, 2) if mtbf_h is not None else None,
            mttr_horas=round(mttr_h, 2) if mttr_h is not None else None,
            cantidad_paradas_no_programadas=cant_paradas_no_prog,
            cantidad_paradas_programadas=cant_paradas_prog,
            cantidad_ciclos_marcha=cant_ciclos_marcha,
        )
