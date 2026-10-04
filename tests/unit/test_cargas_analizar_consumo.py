"""tests/unit/test_cargas_analizar_consumo.py — Caso de uso de perfilado de consumo sobre la serie agregada de un medidor."""

from datetime import datetime, timedelta, timezone

import pytest

from src.application.use_cases.analizar_consumo import AnalizarConsumoUseCase
from src.domain.cargas.ports import RepositorioSeriePotenciaPort
from src.domain.cargas.value_objects import PatronOperacion
from src.domain.telemetria.exceptions import ZonaHorariaInvalidaError
from src.domain.telemetria.value_objects import LecturaPotenciaTemporal

MEDIDOR = "dev-casa"


class MockSerieRepo(RepositorioSeriePotenciaPort):
    def __init__(self, lecturas: list[LecturaPotenciaTemporal] | None = None):
        self.lecturas = lecturas or []
        self.llamadas: list[tuple] = []

    def listar_serie_potencia(
        self,
        dispositivo_id: str,
        desde: datetime,
        hasta: datetime | None = None,
        limite: int | None = None,
    ) -> list[LecturaPotenciaTemporal]:
        self.llamadas.append((dispositivo_id, desde, hasta, limite))
        return self.lecturas[:limite] if limite is not None else self.lecturas

    def obtener_energia_consumida_kwh(
        self, dispositivo_id: str, desde: datetime, hasta: datetime | None = None
    ) -> float | None:
        return None


def _casa(dias: int = 4) -> list[LecturaPotenciaTemporal]:
    """Casa con refrigeración ciclando sobre una base de 40 W de standby."""
    fin = datetime.now(timezone.utc)
    muestras = dias * 24 * 12
    lecturas = []
    for i in range(muestras):
        momento = fin - timedelta(seconds=(muestras - i) * 300)
        potencia = 40.0 + (120.0 if i % 14 < 5 else 0.0)
        lecturas.append(
            LecturaPotenciaTemporal(momento=momento, potencia_w=potencia, potencia_reactiva_var=potencia * 0.8)
        )
    return lecturas


def test_zona_horaria_invalida_es_rechazada_antes_de_leer_la_base():
    repo = MockSerieRepo(_casa())

    with pytest.raises(ZonaHorariaInvalidaError):
        AnalizarConsumoUseCase(repo).perfilar(MEDIDOR, zona="Marte/Olympus")

    assert repo.llamadas == []


def test_sin_datos_el_perfil_no_afirma_nada_pero_responde():
    perfil = AnalizarConsumoUseCase(MockSerieRepo([])).perfilar(MEDIDOR)

    assert perfil.cantidad_lecturas == 0
    assert perfil.linea_base.linea_base_nocturna_W is None
    assert perfil.umbral_ciclos_W is None
    assert perfil.ciclos_sobre_linea_base.ciclos == 0
    assert perfil.ciclos_sobre_linea_base.patron == PatronOperacion.INDETERMINADO


def test_el_umbral_de_ciclos_se_pone_por_encima_de_la_linea_base():
    """Pegado a la base, el ruido del fondo generaría encendidos fantasma."""
    perfil = AnalizarConsumoUseCase(MockSerieRepo(_casa())).perfilar(MEDIDOR)

    assert perfil.linea_base.linea_base_nocturna_W == 40.0
    assert perfil.umbral_ciclos_W == 46.0


def test_el_ciclado_de_refrigeracion_se_detecta_sobre_la_linea_base():
    perfil = AnalizarConsumoUseCase(MockSerieRepo(_casa())).perfilar(MEDIDOR)

    ciclos = perfil.ciclos_sobre_linea_base
    assert ciclos.ciclos > 10
    assert ciclos.patron == PatronOperacion.CICLICO_TERMOSTATICO
    assert ciclos.duracion_encendido_mediana_s == 1500.0
    assert ciclos.duracion_apagado_mediana_s == 3000.0
    assert ciclos.periodo_mediano_s == 4500.0


def test_el_perfil_siempre_declara_el_limite_de_cadencia():
    """El consumidor tiene que poder distinguir "no hubo" de "no se pudo ver"."""
    perfil = AnalizarConsumoUseCase(MockSerieRepo(_casa())).perfilar(MEDIDOR)

    assert perfil.advertencia_cadencia is not None
    assert "300 s" in perfil.advertencia_cadencia
    assert "pava" in perfil.advertencia_cadencia


def test_el_perfil_incluye_los_regimenes_del_segmentador_ya_existente():
    """No se reimplementa la partición modal: se consume la que ya está en producción."""
    perfil = AnalizarConsumoUseCase(MockSerieRepo(_casa())).perfilar(MEDIDOR)

    assert len(perfil.regimenes) >= 2
    assert perfil.regimenes[0].potencia_tipica_w < perfil.regimenes[-1].potencia_tipica_w


def test_se_marca_cuando_la_lectura_fue_truncada_por_el_limite():
    perfil = AnalizarConsumoUseCase(MockSerieRepo(_casa())).perfilar(MEDIDOR, limite=100)

    assert perfil.cantidad_lecturas == 100
    assert perfil.lecturas_truncadas is True


def test_la_ventana_pedida_se_traslada_al_repositorio():
    repo = MockSerieRepo(_casa())

    AnalizarConsumoUseCase(repo).perfilar(MEDIDOR, dias=7)

    dispositivo, desde, hasta, _ = repo.llamadas[0]
    assert dispositivo == MEDIDOR
    assert hasta is not None
    assert 6.9 < (hasta - desde).total_seconds() / 86400 < 7.1
