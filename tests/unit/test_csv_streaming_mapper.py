"""tests/unit/test_csv_streaming_mapper.py."""

from datetime import datetime, timezone

from src.application.mappers.csv_streaming_mapper import (
    BOM_UTF8,
    CsvStreamingMapper,
    formatear_fila_csv,
)
from src.domain.cargas.entities import IntervaloActividadCarga
from src.domain.disponibilidad.entities import EventoDisponibilidad
from src.domain.disponibilidad.value_objects import EstadoMaquina, OrigenClasificacion, TipoParada
from src.domain.telemetria.entities import LecturaInstantanea, MedicionFase
from src.domain.telemetria.value_objects import (
    Corriente,
    FactorPotencia,
    PotenciaActiva,
    Tension,
)


def test_formatear_fila_csv():
    fila = formatear_fila_csv(["valor1", 123, "con, coma", 'con "comillas"'])
    assert 'valor1,123,"con, coma","con ""comillas"""\r\n' == fila


def test_generar_csv_telemetria_con_bom_y_headers():
    ahora = datetime(2026, 9, 7, 10, 0, 0, tzinfo=timezone.utc)
    fase = MedicionFase(
        tension=Tension(voltios=220.0),
        corriente=Corriente(amperios=10.0),
        potencia_activa=PotenciaActiva(vatios=2200.0),
    )
    lectura = LecturaInstantanea(
        id=1,
        dispositivo_id="dev-123",
        registrado_en=ahora,
        fase_r=fase,
        fase_s=fase,
        fase_t=fase,
        potencia_activa_total=PotenciaActiva(vatios=6600.0),
        factor_potencia_total=FactorPotencia(valor=0.98),
        desbalance_tension_porcentaje=1.25,
    )

    generador = CsvStreamingMapper.generar_csv_telemetria(iter([lectura]))
    chunks = list(generador)

    assert len(chunks) == 3
    assert chunks[0] == BOM_UTF8
    assert "timestamp_utc,potencia_activa_total_w" in chunks[1]
    assert "2026-09-07T10:00:00+00:00,6600.00,2200.00" in chunks[2]
    assert "0.98,1.25" in chunks[2]


def test_generar_csv_disponibilidad_con_resumen_kpi():
    ahora = datetime(2026, 9, 7, 8, 0, 0, tzinfo=timezone.utc)
    fin = datetime(2026, 9, 7, 9, 30, 0, tzinfo=timezone.utc)
    evento = EventoDisponibilidad(
        id=42,
        maquina_id="maq-1",
        estado=EstadoMaquina.PARADA,
        tipo_parada=TipoParada.NO_PROGRAMADA,
        inicio_at=ahora,
        fin_at=fin,
        potencia_promedio_w=5.4,
        origen=OrigenClasificacion.CORRECCION_HUMANA,
        comentario="Falla en contactor principal",
    )

    generador = CsvStreamingMapper.generar_csv_disponibilidad(
        iter([evento]), resumen_kpi="Resumen OEE: 85.0% | MTBF: 12.0h"
    )
    chunks = list(generador)

    assert chunks[0] == BOM_UTF8
    assert chunks[1] == "# Resumen OEE: 85.0% | MTBF: 12.0h\r\n"
    assert "evento_id,maquina_id,estado,tipo_parada" in chunks[2]
    assert "42,maq-1,PARADA,NO_PROGRAMADA" in chunks[3]
    assert "5400.00,90.00" in chunks[3]  # 5400s y 90 min
    assert "Falla en contactor principal" in chunks[3]


def test_generar_csv_cargas_atribuidas_y_no_atribuidas():
    ahora = datetime(2026, 9, 7, 10, 0, 0, tzinfo=timezone.utc)
    fin = datetime(2026, 9, 7, 10, 15, 0, tzinfo=timezone.utc)

    inter1 = IntervaloActividadCarga(
        id=101,
        dispositivo_id="dev-cargas",
        inicio_at=ahora,
        fin_at=fin,
        carga_id="c-compresor",
        potencia_media_w=4500.0,
        energia_kwh=1.125,
        confianza=0.92,
    )
    inter2 = IntervaloActividadCarga(
        id=102,
        dispositivo_id="dev-cargas",
        inicio_at=fin,
        fin_at=datetime(2026, 9, 7, 10, 30, 0, tzinfo=timezone.utc),
        carga_id=None,
        potencia_media_w=1200.0,
        energia_kwh=0.3,
        confianza=None,
    )

    mapa = {"c-compresor": ("Compresor Tornillo", "COMPRESORES")}
    generador = CsvStreamingMapper.generar_csv_cargas(iter([inter1, inter2]), mapa_cargas=mapa)
    chunks = list(generador)

    assert chunks[0] == BOM_UTF8
    assert "intervalo_id,dispositivo_id,carga_nombre,categoria" in chunks[1]
    assert "101,dev-cargas,Compresor Tornillo,COMPRESORES" in chunks[2]
    assert "ATRIBUIDO" in chunks[2]
    assert "102,dev-cargas,,," in chunks[3]
    assert "NO_ATRIBUIDO" in chunks[3]
