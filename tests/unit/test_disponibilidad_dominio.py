"""Servicios de dominio de disponibilidad: clasificación, calibración por histograma y anti-transitorios."""

import random
from datetime import datetime, timedelta, timezone

from src.domain.disponibilidad.services import (
    CalibradorUmbralService,
    ClasificadorDisponibilidadService,
    FiltroPersistenciaEstadoService,
    SegmentadorRegimenesService,
)
from src.domain.disponibilidad.value_objects import EstadoMaquina, NaturalezaRegimen
from src.domain.telemetria.value_objects import LecturaPotenciaTemporal


def _fecha(segundos: float = 0.0) -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=segundos)


def test_clasificador_evalua_marcha_y_parada_por_umbral():
    assert ClasificadorDisponibilidadService.evaluar(500.0, umbral_marcha_w=100.0) == EstadoMaquina.MARCHA
    assert ClasificadorDisponibilidadService.evaluar(50.0, umbral_marcha_w=100.0) == EstadoMaquina.PARADA
    # El umbral es inclusivo: exactamente en el límite se considera marcha.
    assert ClasificadorDisponibilidadService.evaluar(100.0, umbral_marcha_w=100.0) == EstadoMaquina.MARCHA


def test_calibrador_umbral_insuficientes_lecturas_devuelve_none():
    assert CalibradorUmbralService.calcular_umbral([10.0] * 5) is None


def test_calibrador_umbral_encuentra_valle_en_distribucion_bimodal():
    # Standby ~50W y marcha ~2000W, con ruido gaussiano realista y bien separados.
    rng = random.Random(42)
    parada = [rng.gauss(50.0, 8.0) for _ in range(150)]
    marcha = [rng.gauss(2000.0, 80.0) for _ in range(150)]
    lecturas = parada + marcha

    umbral = CalibradorUmbralService.calcular_umbral(lecturas)

    assert umbral is not None
    assert 100.0 < umbral < 1800.0


def test_calibrador_umbral_distribucion_unimodal_devuelve_none():
    # Una sola campana gaussiana alrededor de 500W: un único estado, sin valle real.
    rng = random.Random(7)
    lecturas = [rng.gauss(500.0, 15.0) for _ in range(300)]
    assert CalibradorUmbralService.calcular_umbral(lecturas) is None


def test_calibrador_construir_histograma_devuelve_un_borde_mas_que_frecuencias():
    # Los bins son de ancho variable (escala log): sin el borde derecho explícito el
    # consumidor no puede reconstruir el último intervalo asumiendo espaciado uniforme.
    lecturas = [float(i) for i in range(30)]
    bordes, frecuencias = CalibradorUmbralService.construir_histograma(lecturas, num_bins=10)
    assert len(frecuencias) == 10
    assert len(bordes) == len(frecuencias) + 1
    assert sum(frecuencias) == len(lecturas)
    assert bordes == sorted(bordes)


def test_filtro_persistencia_no_confirma_pico_transitorio():
    filtro = FiltroPersistenciaEstadoService()
    maquina_id = "maq-1"

    # Estado confirmado: MARCHA. Un único dip a PARADA no debe confirmarse (min_lecturas=3).
    confirmado = filtro.confirmar_cambio(
        maquina_id, EstadoMaquina.MARCHA, EstadoMaquina.PARADA, min_lecturas=3, min_segundos=999.0, ahora=_fecha(0)
    )
    assert confirmado is False

    # Vuelve a MARCHA inmediatamente: el candidato a PARADA se descarta.
    confirmado = filtro.confirmar_cambio(
        maquina_id, EstadoMaquina.MARCHA, EstadoMaquina.MARCHA, min_lecturas=3, min_segundos=999.0, ahora=_fecha(5)
    )
    assert confirmado is False


def test_filtro_persistencia_confirma_tras_min_lecturas():
    filtro = FiltroPersistenciaEstadoService()
    maquina_id = "maq-1"
    kwargs = {"min_lecturas": 3, "min_segundos": 999.0}

    assert (
        filtro.confirmar_cambio(maquina_id, EstadoMaquina.MARCHA, EstadoMaquina.PARADA, ahora=_fecha(0), **kwargs)
        is False
    )
    assert (
        filtro.confirmar_cambio(maquina_id, EstadoMaquina.MARCHA, EstadoMaquina.PARADA, ahora=_fecha(1), **kwargs)
        is False
    )
    assert (
        filtro.confirmar_cambio(maquina_id, EstadoMaquina.MARCHA, EstadoMaquina.PARADA, ahora=_fecha(2), **kwargs)
        is True
    )


def test_filtro_persistencia_confirma_tras_min_segundos():
    filtro = FiltroPersistenciaEstadoService()
    maquina_id = "maq-1"
    kwargs = {"min_lecturas": 999, "min_segundos": 10.0}

    assert (
        filtro.confirmar_cambio(maquina_id, EstadoMaquina.MARCHA, EstadoMaquina.PARADA, ahora=_fecha(0), **kwargs)
        is False
    )
    assert (
        filtro.confirmar_cambio(maquina_id, EstadoMaquina.MARCHA, EstadoMaquina.PARADA, ahora=_fecha(5), **kwargs)
        is False
    )
    assert (
        filtro.confirmar_cambio(maquina_id, EstadoMaquina.MARCHA, EstadoMaquina.PARADA, ahora=_fecha(11), **kwargs)
        is True
    )


def test_filtro_persistencia_sin_cambio_real_no_confirma_y_limpia_pendiente():
    filtro = FiltroPersistenciaEstadoService()
    maquina_id = "maq-1"

    assert (
        filtro.confirmar_cambio(
            maquina_id, EstadoMaquina.MARCHA, EstadoMaquina.MARCHA, min_lecturas=1, min_segundos=0.0, ahora=_fecha(0)
        )
        is False
    )


# --------------------------------------------------------------------------- #
# Segmentación modal en k regímenes                                            #
# --------------------------------------------------------------------------- #


def _bloque(rng: random.Random, centro: float, sigma: float, cantidad: int) -> list[float]:
    return [rng.gauss(centro, sigma) for _ in range(cantidad)]


def _serie(potencias: list[float], cadencia_s: float = 60.0) -> list[LecturaPotenciaTemporal]:
    return [LecturaPotenciaTemporal(momento=_fecha(i * cadencia_s), potencia_w=p) for i, p in enumerate(potencias)]


def _regimen_cercano_a(regimenes, potencia_w: float):
    return min(regimenes, key=lambda r: abs(r.potencia_tipica_w - potencia_w))


def test_segmentador_detecta_tres_regimenes_en_distribucion_trimodal():
    # Standby ~50W, marcha lenta ~500W y marcha plena ~2000W.
    rng = random.Random(1)
    lecturas = _bloque(rng, 50.0, 8.0, 150) + _bloque(rng, 500.0, 20.0, 150) + _bloque(rng, 2000.0, 80.0, 150)

    segmentacion = SegmentadorRegimenesService.analizar(lecturas)

    assert len(segmentacion.regimenes) == 3
    for regimen, centro in zip(segmentacion.regimenes, (50.0, 500.0, 2000.0), strict=True):
        assert abs(regimen.potencia_tipica_w - centro) < 0.25 * centro
        assert 0.30 < regimen.masa < 0.37
    assert segmentacion.diagnostico_modal.es_multimodal_confiable


def test_segmentador_resuelve_standby_angosto_y_marcha_ancha():
    # La ganancia concreta del binning logarítmico: con ancho de bin fijo en watts el
    # rango lo fija la marcha (~3kW) y las 200 lecturas de standby colapsan en un bin.
    rng = random.Random(11)
    lecturas = _bloque(rng, 20.0, 2.0, 200) + _bloque(rng, 3000.0, 400.0, 200)

    segmentacion = SegmentadorRegimenesService.analizar(lecturas)

    assert len(segmentacion.regimenes) == 2
    standby, marcha = segmentacion.regimenes
    assert abs(standby.potencia_tipica_w - 20.0) < 5.0
    assert abs(marcha.potencia_tipica_w - 3000.0) < 600.0
    # El standby ocupa varios bins, no uno solo: es lo que permite hallar su moda.
    bins_del_standby = sum(
        1 for f, b in zip(segmentacion.frecuencias, segmentacion.bordes_bins_w[:-1], strict=True) if f > 0 and b < 40.0
    )
    assert bins_del_standby >= 3


def test_segmentador_unimodal_no_inventa_regimenes():
    rng = random.Random(7)
    segmentacion = SegmentadorRegimenesService.analizar(_bloque(rng, 500.0, 15.0, 300))

    assert len(segmentacion.regimenes) == 1
    assert segmentacion.umbral_marcha_sugerido_w is None
    assert segmentacion.diagnostico_modal.es_multimodal_confiable is False


def test_barrido_descarta_diente_que_solo_es_pico_sin_suavizado():
    # Dos campanas reales más un diente de un solo bin. Sin suavizar parece una tercera
    # moda; en cuanto se suavisa desaparece. El barrido es lo que distingue la estructura
    # que sobrevive a un rango de anchos de la que vive en una sola ventana.
    conteos = [1, 4, 20, 40, 20, 4, 1, 0, 0, 12, 0, 0, 1, 4, 20, 40, 20, 4, 1, 0]

    sin_suavizar = SegmentadorRegimenesService._seleccionar_modas(
        SegmentadorRegimenesService._suavizar(conteos, 1), 0.25
    )
    suavizado = SegmentadorRegimenesService._seleccionar_modas(SegmentadorRegimenesService._suavizar(conteos, 3), 0.25)

    assert len(sin_suavizar) == 3
    assert len(suavizado) == 2

    diagnostico = SegmentadorRegimenesService._barrer_ancho_banda(conteos, 0.25)
    assert diagnostico.num_modas_estable == 2
    assert diagnostico.fraccion_ventanas_consistentes < 1.0


def test_segmentador_no_se_rompe_con_potencias_no_positivas():
    # El repositorio no filtra negativos: ruido de medición cerca de cero, o flujo inverso.
    rng = random.Random(13)
    lecturas = [-0.4, 0.0, -1.2, *_bloque(rng, 30.0, 4.0, 100), *_bloque(rng, 900.0, 40.0, 100)]

    segmentacion = SegmentadorRegimenesService.analizar(lecturas)

    assert segmentacion.lecturas_no_positivas == 3
    assert len(segmentacion.regimenes) == 2
    assert len(segmentacion.bordes_bins_w) == len(segmentacion.frecuencias) + 1


# --------------------------------------------------------------------------- #
# Dinámica temporal: régimen transitorio vs. régimen estable poco usado         #
# --------------------------------------------------------------------------- #


def test_segmentador_distingue_regimen_raro_estable_de_regimen_transitorio():
    # Dos regímenes de masa parecida y baja. Uno (400W) aparece en tramos contiguos: la
    # máquina se queda ahí, solo que poco. El otro (1000W) aparece siempre aislado entre
    # standby y marcha: es el paso rápido de una a otra. La distribución marginal los ve
    # igual; solo |ΔP|/Δt los separa.
    rng = random.Random(3)
    potencias: list[float] = []
    for _ in range(20):
        potencias += _bloque(rng, 25.0, 2.5, 6)
        potencias.append(rng.gauss(1000.0, 100.0))
        potencias += _bloque(rng, 2500.0, 250.0, 6)
        potencias.append(rng.gauss(1000.0, 100.0))
    for _ in range(6):
        potencias += _bloque(rng, 400.0, 40.0, 10)

    segmentacion = SegmentadorRegimenesService.analizar_serie(_serie(potencias))

    raro_estable = _regimen_cercano_a(segmentacion.regimenes, 400.0)
    transitorio = _regimen_cercano_a(segmentacion.regimenes, 1000.0)
    marcha = _regimen_cercano_a(segmentacion.regimenes, 2500.0)

    assert raro_estable is not transitorio
    assert raro_estable.masa < 0.25 and transitorio.masa < 0.25  # ambos son minoritarios
    assert raro_estable.naturaleza == NaturalezaRegimen.ESTABLE
    assert transitorio.naturaleza == NaturalezaRegimen.TRANSITORIO
    assert transitorio.variacion_mediana_w_s > raro_estable.variacion_mediana_w_s
    # La marcha es la más ruidosa en W/s absolutos y aun así es estable: el criterio se
    # mide contra el ancho de banda del propio régimen, no contra una tasa global.
    assert marcha.naturaleza == NaturalezaRegimen.ESTABLE
    assert marcha.variacion_mediana_w_s > raro_estable.variacion_mediana_w_s


def test_segmentador_sin_serie_temporal_deja_naturaleza_indeterminada():
    rng = random.Random(17)
    segmentacion = SegmentadorRegimenesService.analizar(_bloque(rng, 40.0, 5.0, 150) + _bloque(rng, 1500.0, 60.0, 150))

    for regimen in segmentacion.regimenes:
        assert regimen.naturaleza == NaturalezaRegimen.INDETERMINADO
        assert regimen.variacion_mediana_w_s is None


def test_estimar_cadencia_ignora_huecos_de_datos():
    # Un hueco de varias horas entre dos lecturas no es una transición de la máquina.
    lecturas = [
        LecturaPotenciaTemporal(momento=_fecha(0), potencia_w=20.0),
        LecturaPotenciaTemporal(momento=_fecha(300), potencia_w=22.0),
        LecturaPotenciaTemporal(momento=_fecha(600), potencia_w=21.0),
        LecturaPotenciaTemporal(momento=_fecha(20000), potencia_w=2000.0),
    ]

    cadencia = SegmentadorRegimenesService._estimar_cadencia_nominal(lecturas)
    tasas = SegmentadorRegimenesService._tasas_de_variacion(lecturas, cadencia)

    assert cadencia == 300.0
    assert len(tasas) == 2  # el salto de 20000s queda descartado


# --------------------------------------------------------------------------- #
# Estacionariedad                                                              #
# --------------------------------------------------------------------------- #


def test_estacionariedad_detecta_corrimiento_de_la_moda_de_marcha():
    # El proceso cambia a mitad de ventana (otro producto): un histograma agregado sobre
    # los 4 tramos fundiría las dos campanas de marcha en una sola, ancha y falsa.
    rng = random.Random(5)
    primera = _bloque(rng, 30.0, 4.0, 200) + _bloque(rng, 2000.0, 50.0, 200)
    segunda = _bloque(rng, 30.0, 4.0, 200) + _bloque(rng, 2600.0, 50.0, 200)
    rng.shuffle(primera)
    rng.shuffle(segunda)

    diagnostico = SegmentadorRegimenesService.evaluar_estacionariedad(_serie(primera + segunda))

    assert diagnostico.es_estacionario is False
    assert diagnostico.desplazamiento_maximo_w > 300.0


def test_estacionariedad_no_marca_deriva_cuando_el_proceso_es_estable():
    rng = random.Random(23)
    potencias: list[float] = []
    for _ in range(4):
        tramo = _bloque(rng, 30.0, 4.0, 200) + _bloque(rng, 2000.0, 50.0, 200)
        rng.shuffle(tramo)
        potencias += tramo

    diagnostico = SegmentadorRegimenesService.evaluar_estacionariedad(_serie(potencias))

    assert diagnostico.es_estacionario is True
