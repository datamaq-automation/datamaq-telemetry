import csv
import io
from collections.abc import Generator, Iterator, Sequence
from typing import Any

from src.domain.cargas.entities import IntervaloActividadCarga
from src.domain.disponibilidad.entities import EventoDisponibilidad
from src.domain.telemetria.entities import LecturaInstantanea

BOM_UTF8 = "\ufeff"

HEADER_TELEMETRIA = [
    "timestamp_utc",
    "potencia_activa_total_w",
    "potencia_l1_w",
    "potencia_l2_w",
    "potencia_l3_w",
    "tension_l1_v",
    "tension_l2_v",
    "tension_l3_v",
    "corriente_l1_a",
    "corriente_l2_a",
    "corriente_l3_a",
    "factor_potencia",
    "desbalance_tension_pct",
]

HEADER_DISPONIBILIDAD = [
    "evento_id",
    "maquina_id",
    "estado",
    "tipo_parada",
    "inicio_utc",
    "fin_utc",
    "duracion_segundos",
    "duracion_minutos",
    "potencia_promedio_w",
    "origen_clasificacion",
    "comentario",
]

HEADER_CARGAS = [
    "intervalo_id",
    "dispositivo_id",
    "carga_nombre",
    "categoria",
    "inicio_utc",
    "fin_utc",
    "duracion_minutos",
    "potencia_media_w",
    "energia_estimada_kwh",
    "confianza_pct",
    "estado_atribucion",
]


def formatear_fila_csv(valores: Sequence[Any]) -> str:
    """Convierte una tupla/lista de valores a una línea CSV según RFC 4180."""
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(valores)
    return output.getvalue()


class CsvStreamingMapper:
    """Mapeador para generación en streaming O(1) de datos tabulares en formato CSV."""

    @staticmethod
    def generar_csv_telemetria(
        lecturas: Iterator[LecturaInstantanea],
    ) -> Generator[str, None, None]:
        """Genera el flujo CSV de lecturas de telemetría con BOM UTF-8 inicial."""
        yield BOM_UTF8
        yield formatear_fila_csv(HEADER_TELEMETRIA)

        for item in lecturas:
            p_tot = f"{item.potencia_activa_total.vatios:.2f}" if item.potencia_activa_total else ""
            p_r = f"{item.fase_r.potencia_activa.vatios:.2f}" if item.fase_r.potencia_activa else ""
            p_s = f"{item.fase_s.potencia_activa.vatios:.2f}" if item.fase_s.potencia_activa else ""
            p_t = f"{item.fase_t.potencia_activa.vatios:.2f}" if item.fase_t.potencia_activa else ""

            v_r = f"{item.fase_r.tension.voltios:.2f}" if item.fase_r.tension else ""
            v_s = f"{item.fase_s.tension.voltios:.2f}" if item.fase_s.tension else ""
            v_t = f"{item.fase_t.tension.voltios:.2f}" if item.fase_t.tension else ""

            i_r = f"{item.fase_r.corriente.amperios:.2f}" if item.fase_r.corriente else ""
            i_s = f"{item.fase_s.corriente.amperios:.2f}" if item.fase_s.corriente else ""
            i_t = f"{item.fase_t.corriente.amperios:.2f}" if item.fase_t.corriente else ""

            fp_tot = f"{item.factor_potencia_total.valor:.2f}" if item.factor_potencia_total else ""
            desb = f"{item.desbalance_tension_porcentaje:.2f}" if item.desbalance_tension_porcentaje is not None else ""

            fila = [
                item.registrado_en.isoformat(),
                p_tot,
                p_r,
                p_s,
                p_t,
                v_r,
                v_s,
                v_t,
                i_r,
                i_s,
                i_t,
                fp_tot,
                desb,
            ]
            yield formatear_fila_csv(fila)

    @staticmethod
    def generar_csv_disponibilidad(
        eventos: Iterator[EventoDisponibilidad],
        resumen_kpi: str | None = None,
    ) -> Generator[str, None, None]:
        """Genera el flujo CSV de eventos de disponibilidad con metadatos opcionales."""
        yield BOM_UTF8
        if resumen_kpi:
            yield f"# {resumen_kpi}\r\n"
        yield formatear_fila_csv(HEADER_DISPONIBILIDAD)

        for ev in eventos:
            dur_s = ev.duracion_segundos
            dur_min = (dur_s / 60.0) if dur_s is not None else None
            fila = [
                str(ev.id) if ev.id is not None else "",
                ev.maquina_id,
                ev.estado.value,
                ev.tipo_parada.value if ev.tipo_parada else "",
                ev.inicio_at.isoformat(),
                ev.fin_at.isoformat() if ev.fin_at else "",
                f"{dur_s:.2f}" if dur_s is not None else "",
                f"{dur_min:.2f}" if dur_min is not None else "",
                f"{ev.potencia_promedio_w:.2f}" if ev.potencia_promedio_w is not None else "",
                ev.origen.value,
                ev.comentario or "",
            ]
            yield formatear_fila_csv(fila)

    @staticmethod
    def generar_csv_cargas(
        intervalos: Iterator[IntervaloActividadCarga],
        mapa_cargas: dict[str, tuple[str, str]] | None = None,
    ) -> Generator[str, None, None]:
        """Genera el flujo CSV de intervalos de actividad y atribución NILM."""
        yield BOM_UTF8
        yield formatear_fila_csv(HEADER_CARGAS)

        mapa = mapa_cargas or {}
        for inter in intervalos:
            carga_info = mapa.get(inter.carga_id or "", ("", ""))
            dur_min = inter.duracion_segundos / 60.0
            fila = [
                str(inter.id) if inter.id is not None else "",
                inter.dispositivo_id,
                carga_info[0] if inter.carga_id else "",
                carga_info[1] if inter.carga_id else "",
                inter.inicio_at.isoformat(),
                inter.fin_at.isoformat(),
                f"{dur_min:.2f}",
                f"{inter.potencia_media_w:.2f}" if inter.potencia_media_w is not None else "",
                f"{inter.energia_kwh:.4f}" if inter.energia_kwh is not None else "",
                f"{(inter.confianza * 100.0):.1f}" if inter.confianza is not None else "",
                "ATRIBUIDO" if inter.esta_atribuido else "NO_ATRIBUIDO",
            ]
            yield formatear_fila_csv(fila)
