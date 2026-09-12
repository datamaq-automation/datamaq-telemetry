"""tests/unit/test_cargas_batch_atribucion.py — Caso de uso batch: idempotencia, protección de correcciones y corrección humana."""

from datetime import datetime, timedelta, timezone

import pytest

from src.application.dtos.carga_dto import CorregirIntervaloRequestDTO
from src.application.use_cases.atribuir_consumo import AtribuirConsumoUseCase
from src.domain.cargas.entities import Carga, IntervaloActividadCarga
from src.domain.cargas.exceptions import (
    CargaNoEncontradaError,
    IntervaloActividadNoEncontradoError,
)
from src.domain.cargas.ports import (
    RepositorioIntervalosActividadPort,
    RepositorioSeriePotenciaPort,
)
from src.domain.cargas.value_objects import (
    FirmaCarga,
    NaturalezaElectrica,
    OrigenClasificacionCarga,
    OrigenFirma,
)
from src.domain.telemetria.value_objects import LecturaPotenciaTemporal
from tests.unit.test_cargas_catalogo import MockCargasRepo

MEDIDOR = "dev-casa"
INICIO = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
HASTA = INICIO + timedelta(days=1)


class MockSerieRepo(RepositorioSeriePotenciaPort):
    def __init__(self, lecturas=None, energia_kwh=None):
        self.lecturas = lecturas or []
        self.energia_kwh = energia_kwh

    def listar_serie_potencia(self, dispositivo_id, desde, hasta=None, limite=None):
        return self.lecturas

    def obtener_energia_consumida_kwh(self, dispositivo_id, desde, hasta):
        return self.energia_kwh


class MockIntervalosRepo(RepositorioIntervalosActividadPort):
    def __init__(self):
        self.intervalos: list[IntervaloActividadCarga] = []
        self._siguiente_id = 1

    def obtener_por_id(self, intervalo_id):
        return next((i for i in self.intervalos if i.id == intervalo_id), None)

    def listar_por_dispositivo(self, dispositivo_id, desde, hasta):
        return [i for i in self.intervalos if i.dispositivo_id == dispositivo_id and desde <= i.inicio_at <= hasta]

    def listar_por_carga(self, carga_id, limite=100):
        return [i for i in self.intervalos if i.carga_id == carga_id][:limite]

    def guardar(self, intervalo):
        if intervalo.id is None:
            intervalo.id = self._siguiente_id
            self._siguiente_id += 1
            self.intervalos.append(intervalo)
        return intervalo

    def reemplazar_ventana(self, dispositivo_id, desde, hasta, intervalos):
        protegidas = {
            (i.inicio_at, i.fin_at)
            for i in self.intervalos
            if i.dispositivo_id == dispositivo_id and i.es_correccion_humana
        }
        self.intervalos = [
            i
            for i in self.intervalos
            if i.dispositivo_id != dispositivo_id
            or not (desde <= i.inicio_at <= hasta)
            or (i.inicio_at, i.fin_at) in protegidas
        ]
        escritos = 0
        for intervalo in intervalos:
            if (intervalo.inicio_at, intervalo.fin_at) in protegidas:
                continue
            self.guardar(intervalo)
            escritos += 1
        return escritos


def _serie_con_termotanque(ciclos: int = 2) -> list[LecturaPotenciaTemporal]:
    """Casa con base de 120 W y encendidos de ~1800 W de 40 min, a cadencia de 5 min."""
    muestras: list[tuple[float, float]] = []
    for _ in range(ciclos):
        muestras += [(120.0, 90.0)] * 12 + [(1920.0, 100.0)] * 8
    muestras += [(120.0, 90.0)] * 12
    return [
        LecturaPotenciaTemporal(momento=INICIO + timedelta(seconds=i * 300), potencia_w=p, potencia_reactiva_var=q)
        for i, (p, q) in enumerate(muestras)
    ]


def _termotanque() -> Carga:
    return Carga(
        id="carga-termo",
        dispositivo_id=MEDIDOR,
        nombre="Termotanque",
        naturaleza_electrica=NaturalezaElectrica.RESISTIVA,
        firma=FirmaCarga(
            potencia_w=1800.0,
            dispersion_w=90.0,
            factor_potencia=0.99,
            duracion_encendido_s=2400.0,
            origen=OrigenFirma.CAMPANA,
        ),
    )


def _use_case(lecturas=None, cargas=None, energia=None):
    repo_cargas = MockCargasRepo()
    for carga in cargas or []:
        repo_cargas.guardar(carga)
    intervalos = MockIntervalosRepo()
    return (
        AtribuirConsumoUseCase(MockSerieRepo(lecturas, energia), repo_cargas, intervalos),
        intervalos,
        repo_cargas,
    )


def test_sin_cargas_con_firma_todo_queda_sin_atribuir_y_se_avisa():
    use_case, _, _ = _use_case(_serie_con_termotanque())

    resultado = use_case.analizar(MEDIDOR, desde=INICIO, hasta=HASTA)

    assert resultado.cargas_con_firma == 0
    assert resultado.atribuidos == 0
    assert resultado.advertencia_cadencia is not None
    assert "campaña de caracterización" in resultado.advertencia_cadencia


def test_el_batch_detecta_y_atribuye_los_episodios():
    use_case, intervalos, _ = _use_case(_serie_con_termotanque(), [_termotanque()])

    resultado = use_case.analizar(MEDIDOR, desde=INICIO, hasta=HASTA)

    assert resultado.episodios_detectados == 2
    assert resultado.atribuidos == 2
    assert all(i.carga_id == "carga-termo" for i in intervalos.intervalos)


def test_re_correr_la_misma_ventana_no_duplica_intervalos():
    """Los límites del episodio son deterministas: reprocesar debe reescribir, no sumar."""
    use_case, intervalos, _ = _use_case(_serie_con_termotanque(), [_termotanque()])

    use_case.analizar(MEDIDOR, desde=INICIO, hasta=HASTA)
    use_case.analizar(MEDIDOR, desde=INICIO, hasta=HASTA)

    assert len(intervalos.intervalos) == 2


def test_el_batch_no_pisa_una_correccion_humana():
    """Esas filas son el dataset etiquetado: es lo único que ninguna regla puede regenerar."""
    use_case, intervalos, _ = _use_case(_serie_con_termotanque(), [_termotanque()])
    use_case.analizar(MEDIDOR, desde=INICIO, hasta=HASTA)
    corregido = intervalos.intervalos[0]
    corregido.corregir("carga-termo", usuario_id="u1", notas="confirmado a mano")

    use_case.analizar(MEDIDOR, desde=INICIO, hasta=HASTA)

    sobreviviente = next(i for i in intervalos.intervalos if i.inicio_at == corregido.inicio_at)
    assert sobreviviente.es_correccion_humana is True
    assert sobreviviente.notas == "confirmado a mano"


def test_la_atribucion_reparte_los_kwh_contra_el_contador():
    use_case, _, _ = _use_case(_serie_con_termotanque(), [_termotanque()], energia=5.0)
    use_case.analizar(MEDIDOR, desde=INICIO, hasta=HASTA)

    atribucion = use_case.atribucion(MEDIDOR)

    assert atribucion.energia_total_kwh == 5.0
    assert atribucion.energia_atribuida_kwh > 0
    assert atribucion.residual_kwh is not None
    assert any(i.nombre == "Termotanque" for i in atribucion.items)


def test_corregir_un_intervalo_lo_reimputa_y_lo_marca():
    use_case, intervalos, _ = _use_case(_serie_con_termotanque(), [_termotanque()])
    use_case.analizar(MEDIDOR, desde=INICIO, hasta=HASTA)
    intervalo_id = intervalos.intervalos[0].id

    dto = use_case.corregir_intervalo(
        intervalo_id, CorregirIntervaloRequestDTO(carga_id=None, notas="no fue el termotanque"), "u1"
    )

    assert dto.carga_id is None
    assert dto.origen == OrigenClasificacionCarga.CORRECCION_HUMANA
    assert dto.corregido_por_usuario_id == "u1"


def test_corregir_hacia_una_carga_inexistente_falla():
    use_case, intervalos, _ = _use_case(_serie_con_termotanque(), [_termotanque()])
    use_case.analizar(MEDIDOR, desde=INICIO, hasta=HASTA)

    with pytest.raises(CargaNoEncontradaError):
        use_case.corregir_intervalo(
            intervalos.intervalos[0].id, CorregirIntervaloRequestDTO(carga_id="no-existe"), "u1"
        )


def test_corregir_un_intervalo_inexistente_falla():
    use_case, _, _ = _use_case()

    with pytest.raises(IntervaloActividadNoEncontradoError):
        use_case.corregir_intervalo(999, CorregirIntervaloRequestDTO(carga_id=None), "u1")


def test_sin_datos_el_batch_no_falla_ni_escribe():
    use_case, intervalos, _ = _use_case([])

    resultado = use_case.analizar(MEDIDOR, desde=INICIO, hasta=HASTA)

    assert resultado.cantidad_lecturas == 0
    assert resultado.episodios_detectados == 0
    assert intervalos.intervalos == []
