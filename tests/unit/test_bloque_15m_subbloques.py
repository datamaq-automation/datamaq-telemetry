"""tests/unit/test_bloque_15m_subbloques.py — valor de bloque de 15 min = promedio de sus tres sub-bloques de 5 min.

Decisión 2026-10-11 (punto 2): el bloque 12:00-12:15 vale la media de los bloques 12:00-12:04, 12:05-12:09 y
12:10-12:14, no la media simple de sus muestras. El pico de potencia del histórico de nodo sale de las muestras
crudas, no de los bloques ya promediados.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.application.use_cases.agregacion_dispositivos import calcular_historico
from src.domain.telemetria.entities import LecturaInstantanea, MedicionFase
from src.domain.telemetria.servicios.agregador_dispositivos import AgregadorDispositivosService
from src.domain.telemetria.servicios.agregador_lecturas import AgregadorLecturasService
from src.domain.telemetria.servicios.promedio_subbloques import promedio_por_subbloques
from src.domain.telemetria.value_objects import PotenciaActiva, PotenciaReactiva

INICIO = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)  # inicio de bloque de 15 min
BLOQUE = 900


def _t(segundos: int) -> datetime:
    return INICIO + timedelta(seconds=segundos)


# Sub-bloque 00-04: 1 muestra de 1000 W; 05-09: 3 de 2000 W; 10-14: 2 de 4000 W.
# Media de muestras = 2500 W (la que se usaba). Media de los tres sub-bloques = 2333,33 W (la de la decisión).
MUESTRAS_DESIGUALES = [(60, 1000.0), (360, 2000.0), (420, 2000.0), (480, 2000.0), (660, 4000.0), (780, 4000.0)]


class TestPromedioPorSubbloques:
    def test_ejemplo_de_la_decision_es_2333_33_y_no_2500(self):
        pares = [(_t(s), w) for s, w in MUESTRAS_DESIGUALES]
        valor = promedio_por_subbloques([(p[0].timestamp(), p[1]) for p in pares], BLOQUE)

        assert valor == pytest.approx(7000.0 / 3.0)
        assert valor != pytest.approx(2500.0)

    def test_muestreo_uniforme_coincide_con_la_media_simple(self):
        # Una muestra por sub-bloque: la media de sub-bloques es la media simple.
        pares = [(_t(60).timestamp(), 1000.0), (_t(360).timestamp(), 2000.0), (_t(660).timestamp(), 3000.0)]

        assert promedio_por_subbloques(pares, BLOQUE) == pytest.approx(2000.0)

    def test_sin_muestras_no_hay_valor(self):
        assert promedio_por_subbloques([], BLOQUE) is None

    def test_intervalo_distinto_de_15_min_usa_la_media_simple_del_bloque(self):
        # Con bloques de 5 min, el sub-bloque es el propio bloque: media simple.
        pares = [(_t(10).timestamp(), 1000.0), (_t(20).timestamp(), 3000.0)]

        assert promedio_por_subbloques(pares, 300) == pytest.approx(2000.0)


class TestAgregadorDispositivosSubbloques:
    def test_promedio_del_bloque_es_2333_33_y_pico_es_la_muestra_maxima(self):
        lecturas = {"A": [(_t(s), w) for s, w in MUESTRAS_DESIGUALES]}
        puntos = AgregadorDispositivosService.sumar_potencia_en_el_tiempo(lecturas, BLOQUE)

        assert len(puntos) == 1
        assert puntos[0].potencia_activa_total_w == pytest.approx(7000.0 / 3.0, abs=0.01)
        assert puntos[0].demanda_max_w == 4000.0

    def test_suma_entre_medidores_de_medias_por_subbloque(self):
        # Medidor B con muestreo uniforme: sus tres sub-bloques valen 1500 W cada uno.
        lecturas = {
            "A": [(_t(s), w) for s, w in MUESTRAS_DESIGUALES],
            "B": [(_t(60), 1500.0), (_t(360), 1500.0), (_t(660), 1500.0)],
        }
        puntos = AgregadorDispositivosService.sumar_potencia_en_el_tiempo(lecturas, BLOQUE)

        assert puntos[0].potencia_activa_total_w == pytest.approx(7000.0 / 3.0 + 1500.0, abs=0.01)


class TestAgregadorLecturasSubbloques:
    def test_bloque_instantaneo_usa_media_de_subbloques_para_p_y_q(self):
        lecturas = [
            LecturaInstantanea(
                id=None,
                dispositivo_id="A",
                registrado_en=_t(s),
                fase_r=MedicionFase(),
                fase_s=MedicionFase(),
                fase_t=MedicionFase(),
                potencia_activa_total=PotenciaActiva(w),
                potencia_reactiva_total=PotenciaReactiva(w / 10.0),
            )
            for s, w in MUESTRAS_DESIGUALES
        ]
        agregadas = AgregadorLecturasService.agregar_lecturas_en_intervalo(lecturas, BLOQUE)

        assert agregadas[0].potencia_activa_total.vatios == pytest.approx(7000.0 / 3.0)
        assert agregadas[0].potencia_reactiva_total.var == pytest.approx(7000.0 / 30.0)
        assert agregadas[0].demanda_max_w == 4000.0

        # S y FP de la misma fila: recompuestos desde P y Q del bloque (una sola base).
        p = agregadas[0].potencia_activa_total.vatios
        q = agregadas[0].potencia_reactiva_total.var
        s = agregadas[0].potencia_aparente_total.va
        assert s**2 == pytest.approx(p**2 + q**2, rel=1e-4)
        assert agregadas[0].factor_potencia_total.valor == pytest.approx(p / s, abs=1e-4)

    def test_sin_reactiva_el_bloque_no_tiene_s_ni_fp_de_otra_base(self):
        lecturas = [
            LecturaInstantanea(
                id=None,
                dispositivo_id="A",
                registrado_en=_t(s),
                fase_r=MedicionFase(),
                fase_s=MedicionFase(),
                fase_t=MedicionFase(),
                potencia_activa_total=PotenciaActiva(w),
            )
            for s, w in MUESTRAS_DESIGUALES
        ]
        agregadas = AgregadorLecturasService.agregar_lecturas_en_intervalo(lecturas, BLOQUE)

        assert agregadas[0].potencia_activa_total.vatios == pytest.approx(7000.0 / 3.0)
        assert agregadas[0].potencia_reactiva_total is None
        assert agregadas[0].potencia_aparente_total is None
        assert agregadas[0].factor_potencia_total is None


class _ConsultarFalso:
    """Stub del caso de uso: devuelve muestras crudas y un piso de plan configurable."""

    def __init__(self, muestras_por_dispositivo, piso_segundos: int):
        self._muestras = muestras_por_dispositivo
        self._piso = piso_segundos
        self.lecturas_crudas = self  # mismo contrato que ConsultarTelemetriaUseCase.lecturas_crudas

    def intervalo_minimo_segundos(self, id_o_uid: str) -> int:
        return self._piso

    def listar(self, id_o_uid, limite, desde=None, hasta=None):
        return [
            m for m in self._muestras[id_o_uid] if (desde is None or m[0] >= desde) and (hasta is None or m[0] <= hasta)
        ]


class TestCalcularHistoricoBloque15m:
    def _muestras(self):
        return {"A": [(_t(s), w) for s, w in MUESTRAS_DESIGUALES]}

    def test_historico_15m_devuelve_media_de_subbloques_y_pico_de_muestras(self):
        hasta = _t(BLOQUE)
        consultar = _ConsultarFalso(self._muestras(), piso_segundos=0)
        puntos = calcular_historico(["A"], consultar, "15m", horas=1, hasta=hasta)

        punto = next(p for p in puntos if p.momento == INICIO)
        assert punto.potencia_activa_total_w == pytest.approx(7000.0 / 3.0, abs=0.01)
        assert punto.demanda_max_w == 4000.0

    def test_piso_free_de_15_min_lleva_el_historico_a_bloques_de_15_min(self):
        # Free pide granularidad 5m, pero el piso de 900 s fija la salida en bloques de 15 min.
        hasta = _t(BLOQUE)
        consultar = _ConsultarFalso(self._muestras(), piso_segundos=900)
        puntos = calcular_historico(["A"], consultar, "5m", horas=1, hasta=hasta)

        assert all((p.momento.timestamp() % BLOQUE) == 0 for p in puntos)
        punto = next(p for p in puntos if p.momento == INICIO)
        assert punto.potencia_activa_total_w == pytest.approx(7000.0 / 3.0, abs=0.01)
