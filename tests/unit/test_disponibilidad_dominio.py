"""Servicios de dominio de disponibilidad: clasificación, calibración por histograma y anti-transitorios."""

import random
from datetime import datetime, timedelta, timezone

from src.domain.disponibilidad.services import (
    CalibradorUmbralService,
    ClasificadorDisponibilidadService,
    FiltroPersistenciaEstadoService,
)
from src.domain.disponibilidad.value_objects import EstadoMaquina


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


def test_calibrador_construir_histograma_devuelve_bins_y_frecuencias():
    lecturas = [float(i) for i in range(30)]
    bordes, frecuencias = CalibradorUmbralService.construir_histograma(lecturas, num_bins=10)
    assert len(bordes) == 10
    assert len(frecuencias) == 10
    assert sum(frecuencias) == len(lecturas)


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
