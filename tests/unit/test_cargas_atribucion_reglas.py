"""tests/unit/test_cargas_atribucion_reglas.py — Tests unitarios para la integración del motor de reglas y presets en AtribuirConsumoUseCase."""

from datetime import datetime, timedelta, timezone

from src.application.use_cases.atribuir_consumo import AtribuirConsumoUseCase
from src.domain.cargas.entities import Carga
from src.domain.cargas.value_objects import OrigenClasificacionCarga
from src.domain.telemetria.value_objects import LecturaPotenciaTemporal
from tests.unit.test_cargas_batch_atribucion import MockIntervalosRepo, MockSerieRepo
from tests.unit.test_cargas_catalogo import MockCargasRepo

MEDIDOR = "dev-casa-reglas"
INICIO = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)


def _serie_pulso_pava() -> list[LecturaPotenciaTemporal]:
    """Base de 100 W y un pulso de pava eléctrica de 1850 W (3 minutos) entre muestras."""
    # Muestras a cadencia de 60 s para capturar el pulso (total > 20 lecturas)
    muestras: list[tuple[float, float]] = [(100.0, 70.0)] * 15
    muestras += [(1950.0, 75.0)] * 3  # 3 min a 1850 W delta
    muestras += [(100.0, 70.0)] * 15
    return [
        LecturaPotenciaTemporal(momento=INICIO + timedelta(seconds=i * 60), potencia_w=p, potencia_reactiva_var=q)
        for i, (p, q) in enumerate(muestras)
    ]


def _serie_ciclo_heladera() -> list[LecturaPotenciaTemporal]:
    """Base de 50 W y un ciclo de heladera de 120 W con 90 VAr inductivos durante 20 min."""
    muestras: list[tuple[float, float]] = [(50.0, 10.0)] * 12
    muestras += [(170.0, 100.0)] * 4  # 4 muestras de 300 s = 20 min
    muestras += [(50.0, 10.0)] * 12
    return [
        LecturaPotenciaTemporal(momento=INICIO + timedelta(seconds=i * 300), potencia_w=p, potencia_reactiva_var=q)
        for i, (p, q) in enumerate(muestras)
    ]


def test_atribucion_por_regla_imputa_a_carga_sin_firma_si_nombre_coincide():
    """Si el usuario tiene 'Pava eléctrica' sin firma calibrada, la regla física la reconoce y la imputa."""
    repo_cargas = MockCargasRepo()
    carga_pava = Carga(
        id="carga-pava-sin-firma",
        dispositivo_id=MEDIDOR,
        nombre="Pava eléctrica",
        potencia_nominal_w=1850.0,
        firma=None,  # No tiene firma calibrada todavía
    )
    repo_cargas.guardar(carga_pava)

    repo_serie = MockSerieRepo(lecturas=_serie_pulso_pava(), energia_kwh=0.5)
    repo_intervalos = MockIntervalosRepo()

    uc = AtribuirConsumoUseCase(repo_serie, repo_cargas, repo_intervalos)
    res = uc.analizar(MEDIDOR, desde=INICIO, hasta=INICIO + timedelta(hours=1))

    assert res.episodios_detectados >= 1
    assert res.atribuidos >= 1

    intervalos = repo_intervalos.listar_por_dispositivo(MEDIDOR, INICIO, INICIO + timedelta(hours=1))
    int_pava = next((i for i in intervalos if i.carga_id == "carga-pava-sin-firma"), None)

    assert int_pava is not None
    assert int_pava.origen == OrigenClasificacionCarga.REGLA
    assert int_pava.confianza is not None and int_pava.confianza >= 0.85
    assert "Pava eléctrica" in (int_pava.notas or "")


def test_atribucion_por_regla_registra_sugerencia_cuando_no_hay_carga_en_catalogo():
    """Si no hay heladera en el catálogo, el intervalo queda no atribuido pero con la sugerencia física en notas."""
    repo_cargas = MockCargasRepo()  # Catálogo vacío
    repo_serie = MockSerieRepo(lecturas=_serie_ciclo_heladera(), energia_kwh=0.2)
    repo_intervalos = MockIntervalosRepo()

    uc = AtribuirConsumoUseCase(repo_serie, repo_cargas, repo_intervalos)
    res = uc.analizar(MEDIDOR, desde=INICIO, hasta=INICIO + timedelta(hours=2))

    assert res.episodios_detectados >= 1
    assert res.atribuidos == 0  # No había carga en catálogo para imputar el ID
    assert res.no_atribuidos >= 1

    intervalos = repo_intervalos.listar_por_dispositivo(MEDIDOR, INICIO, INICIO + timedelta(hours=2))
    int_heladera = intervalos[0]

    assert int_heladera.carga_id is None
    assert int_heladera.confianza is not None and int_heladera.confianza >= 0.80
    assert "Sugerido por regla: Heladera" in (int_heladera.notas or "")


def test_inicializar_presets_en_catalogo_crea_cargas_precalibradas():
    """El caso de uso permite inicializar el catálogo del medidor con los presets de fábrica."""
    repo_cargas = MockCargasRepo()
    repo_serie = MockSerieRepo()
    repo_intervalos = MockIntervalosRepo()

    uc = AtribuirConsumoUseCase(repo_serie, repo_cargas, repo_intervalos)
    creadas = uc.inicializar_presets_catalogo(MEDIDOR)

    assert len(creadas) == 9
    nombres = {c.nombre for c in creadas}
    assert "Heladera" in nombres
    assert "Termotanque eléctrico" in nombres
    assert "Computadora / PC" in nombres

    # Si se vuelve a ejecutar, no duplica
    segunda_vez = uc.inicializar_presets_catalogo(MEDIDOR)
    assert len(segunda_vez) == 9
    assert len(repo_cargas.listar_por_dispositivo(MEDIDOR)) == 9


def test_listar_intervalos_dispositivo_filtra_no_atribuidos():
    """El caso de uso permite listar intervalos del medidor filtrando solo los no atribuidos."""
    repo_cargas = MockCargasRepo()
    repo_serie = MockSerieRepo(lecturas=_serie_ciclo_heladera(), energia_kwh=0.2)
    repo_intervalos = MockIntervalosRepo()

    uc = AtribuirConsumoUseCase(repo_serie, repo_cargas, repo_intervalos)
    uc.analizar(MEDIDOR, desde=INICIO, hasta=INICIO + timedelta(hours=2))

    todos = uc.listar_intervalos_dispositivo(MEDIDOR, desde=INICIO, hasta=INICIO + timedelta(hours=2))
    assert len(todos) >= 1

    no_atribuidos = uc.listar_intervalos_dispositivo(
        MEDIDOR, desde=INICIO, hasta=INICIO + timedelta(hours=2), solo_no_atribuidos=True
    )
    assert len(no_atribuidos) == len(todos)
    assert all(not i.esta_atribuido for i in no_atribuidos)
