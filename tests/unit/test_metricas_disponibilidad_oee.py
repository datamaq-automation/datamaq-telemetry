from datetime import datetime, timedelta, timezone

import pytest

from src.domain.disponibilidad.entities import EventoDisponibilidad
from src.domain.disponibilidad.servicios.calculador_metricas_oee import (
    CalculadorMetricasOEEService,
)
from src.domain.disponibilidad.value_objects import EstadoMaquina, TipoParada

T0 = datetime(2026, 9, 7, 8, 0, tzinfo=timezone.utc)


def test_calculo_oee_marcha_continua():
    # 8 horas de turno, 100% en marcha
    fin = T0 + timedelta(hours=8)
    evento = EventoDisponibilidad(
        id=1,
        maquina_id="maq-1",
        estado=EstadoMaquina.MARCHA,
        inicio_at=T0,
        fin_at=fin,
    )
    metricas = CalculadorMetricasOEEService.calcular_metricas([evento], inicio=T0, fin=fin)

    assert metricas.tiempo_total_s == 8 * 3600
    assert metricas.tiempo_marcha_s == 8 * 3600
    assert metricas.tiempo_parada_programada_s == 0.0
    assert metricas.tiempo_parada_no_programada_s == 0.0
    assert metricas.disponibilidad_oee_pct == 100.0
    assert metricas.cantidad_paradas_no_programadas == 0
    assert metricas.mtbf_horas is None
    assert metricas.mttr_horas is None


def test_calculo_oee_con_paradas_programadas_y_no_programadas():
    # 8 horas de turno:
    # 08:00 - 10:00 (2h) Marcha
    # 10:00 - 11:00 (1h) Parada programada (mantenimiento preventivo)
    # 11:00 - 14:00 (3h) Marcha
    # 14:00 - 15:00 (1h) Parada no programada (falla mecánica / avería)
    # 15:00 - 16:00 (1h) Marcha
    #
    # Tiempo total: 8h = 28800s
    # Tiempo parada programada: 1h = 3600s
    # Tiempo planificado de carga: 8h - 1h = 7h = 25200s
    # Tiempo marcha: 2h + 3h + 1h = 6h = 21600s
    # Tiempo parada no programada: 1h = 3600s
    #
    # Disponibilidad OEE: (6h / 7h) * 100 = 85.714%
    # MTBF: 6h / 1 falla = 6.0h
    # MTTR: 1h / 1 falla = 1.0h
    fin = T0 + timedelta(hours=8)
    eventos = [
        EventoDisponibilidad(
            id=1, maquina_id="maq-1", estado=EstadoMaquina.MARCHA, inicio_at=T0, fin_at=T0 + timedelta(hours=2)
        ),
        EventoDisponibilidad(
            id=2,
            maquina_id="maq-1",
            estado=EstadoMaquina.PARADA,
            tipo_parada=TipoParada.PROGRAMADA,
            inicio_at=T0 + timedelta(hours=2),
            fin_at=T0 + timedelta(hours=3),
        ),
        EventoDisponibilidad(
            id=3,
            maquina_id="maq-1",
            estado=EstadoMaquina.MARCHA,
            inicio_at=T0 + timedelta(hours=3),
            fin_at=T0 + timedelta(hours=6),
        ),
        EventoDisponibilidad(
            id=4,
            maquina_id="maq-1",
            estado=EstadoMaquina.PARADA,
            tipo_parada=TipoParada.NO_PROGRAMADA,
            inicio_at=T0 + timedelta(hours=6),
            fin_at=T0 + timedelta(hours=7),
        ),
        EventoDisponibilidad(
            id=5, maquina_id="maq-1", estado=EstadoMaquina.MARCHA, inicio_at=T0 + timedelta(hours=7), fin_at=fin
        ),
    ]

    metricas = CalculadorMetricasOEEService.calcular_metricas(eventos, inicio=T0, fin=fin)

    assert metricas.tiempo_total_s == 8 * 3600
    assert metricas.tiempo_marcha_s == 6 * 3600
    assert metricas.tiempo_parada_programada_s == 1 * 3600
    assert metricas.tiempo_parada_no_programada_s == 1 * 3600
    assert metricas.disponibilidad_oee_pct == pytest.approx(85.714, rel=1e-3)
    assert metricas.cantidad_paradas_no_programadas == 1
    assert metricas.cantidad_paradas_programadas == 1
    assert metricas.cantidad_ciclos_marcha == 3
    assert metricas.mtbf_horas == pytest.approx(6.0)
    assert metricas.mttr_horas == pytest.approx(1.0)


def test_recorte_temporal_en_bordes_de_ventana():
    # Evento arranca 2 horas antes de inicio y termina 2 horas después de fin
    inicio_ventana = T0 + timedelta(hours=2)
    fin_ventana = T0 + timedelta(hours=6)

    evento = EventoDisponibilidad(
        id=1,
        maquina_id="maq-1",
        estado=EstadoMaquina.MARCHA,
        inicio_at=T0,
        fin_at=T0 + timedelta(hours=8),
    )

    metricas = CalculadorMetricasOEEService.calcular_metricas([evento], inicio=inicio_ventana, fin=fin_ventana)

    # Debe recortar estrictamente a las 4 horas de la ventana
    assert metricas.tiempo_total_s == 4 * 3600
    assert metricas.tiempo_marcha_s == 4 * 3600
    assert metricas.disponibilidad_oee_pct == 100.0
