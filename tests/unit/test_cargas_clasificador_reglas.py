"""tests/unit/test_cargas_clasificador_reglas.py — Tests unitarios para el motor de reglas de clasificación y catálogo de presets de cargas."""

from datetime import datetime, timedelta, timezone

from src.domain.cargas.servicios.clasificador_reglas import (
    ClasificadorCargasReglasService,
)
from src.domain.cargas.servicios.presets_cargas import CatalogoPresetsCargas
from src.domain.cargas.value_objects import (
    CategoriaCarga,
    EpisodioCarga,
    NaturalezaElectrica,
)

INICIO = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)


def _episodio(
    delta_w: float,
    duracion_s: float,
    delta_q: float | None = None,
    dispersion_w: float | None = None,
    factor_potencia: float | None = None,
) -> EpisodioCarga:
    return EpisodioCarga(
        inicio=INICIO,
        fin=INICIO + timedelta(seconds=duracion_s),
        delta_w=delta_w,
        delta_reactiva_var=delta_q,
        duracion_s=duracion_s,
        potencia_media_w=delta_w,
        muestras=max(1, int(duracion_s / 300)),
        dispersion_w=dispersion_w,
        factor_potencia=factor_potencia,
    )


# ------------------------------------------------------------- Motores Inductivos


def test_clasificar_heladera_motor_inductivo():
    """Heladera: ~120 W, alta componente inductiva Q (FP ~0.7), ciclado de 15-30 min."""
    episodio = _episodio(delta_w=120.0, duracion_s=1500.0, delta_q=95.0)
    diag = ClasificadorCargasReglasService.clasificar_episodio(episodio)

    assert diag.aparato_sugerido == "Heladera"
    assert diag.categoria == CategoriaCarga.REFRIGERACION
    assert diag.naturaleza_electrica == NaturalezaElectrica.MOTOR
    assert diag.confianza >= 0.80
    assert not diag.es_ambiguo


def test_clasificar_freezer_motor_inductivo():
    """Freezer: ~180 W, inductivo, ciclos más largos (> 30 min)."""
    episodio = _episodio(delta_w=185.0, duracion_s=2100.0, delta_q=135.0)
    diag = ClasificadorCargasReglasService.clasificar_episodio(episodio)

    assert diag.aparato_sugerido == "Freezer"
    assert diag.categoria == CategoriaCarga.REFRIGERACION
    assert diag.naturaleza_electrica == NaturalezaElectrica.MOTOR
    assert diag.confianza >= 0.80


def test_clasificar_refrigeracion_ambigua_en_zona_solape():
    """Zona de solape 135-155 W con duración intermedia: ambas son plausibles."""
    episodio = _episodio(delta_w=145.0, duracion_s=1800.0, delta_q=105.0)
    diag = ClasificadorCargasReglasService.clasificar_episodio(episodio)

    assert diag.categoria == CategoriaCarga.REFRIGERACION
    assert diag.naturaleza_electrica == NaturalezaElectrica.MOTOR
    assert diag.es_ambiguo is True
    assert "Heladera" in diag.alternativas or "Freezer" in diag.alternativas


# ------------------------------------------------------------- Resistivos


def test_clasificar_pava_electrica_pulso_corto_resistivo():
    """Pava: ~1850 W, Q~0 (FP~1), duración ultracorta de 2 a 5 minutos."""
    episodio = _episodio(delta_w=1850.0, duracion_s=180.0, delta_q=8.0)
    diag = ClasificadorCargasReglasService.clasificar_episodio(episodio)

    assert diag.aparato_sugerido == "Pava eléctrica"
    assert diag.categoria == CategoriaCarga.COCCION
    assert diag.naturaleza_electrica == NaturalezaElectrica.RESISTIVA
    assert diag.confianza >= 0.90


def test_clasificar_termotanque_bloque_largo_resistivo():
    """Termotanque: ~1800 W, Q~0, bloque continuo único largo de 30 a 90 min."""
    episodio = _episodio(delta_w=1800.0, duracion_s=2700.0, delta_q=12.0)
    diag = ClasificadorCargasReglasService.clasificar_episodio(episodio)

    assert diag.aparato_sugerido == "Termotanque eléctrico"
    assert diag.categoria == CategoriaCarga.CALENTAMIENTO_AGUA
    assert diag.naturaleza_electrica == NaturalezaElectrica.RESISTIVA
    assert diag.confianza >= 0.85


def test_clasificar_horno_electrico_resistivo_prolongado():
    """Horno: ~2200 W, Q~0, uso culinario prolongado > 45 min."""
    episodio = _episodio(delta_w=2200.0, duracion_s=5400.0, delta_q=15.0)
    diag = ClasificadorCargasReglasService.clasificar_episodio(episodio)

    assert diag.aparato_sugerido == "Horno eléctrico"
    assert diag.categoria == CategoriaCarga.COCCION
    assert diag.naturaleza_electrica == NaturalezaElectrica.RESISTIVA


def test_clasificar_anafe_electrico_resistivo_coccion():
    """Anafe: ~1500 W, Q~0, pulsos térmicos de 10 a 25 min."""
    episodio = _episodio(delta_w=1500.0, duracion_s=900.0, delta_q=10.0)
    diag = ClasificadorCargasReglasService.clasificar_episodio(episodio)

    assert diag.aparato_sugerido == "Anafe eléctrico"
    assert diag.categoria == CategoriaCarga.COCCION
    assert diag.naturaleza_electrica == NaturalezaElectrica.RESISTIVA


def test_clasificar_caloventor_dos_potencias():
    """Caloventor: escalón exacto de 1000 W o 2000 W con leve reactiva del motor forzador."""
    episodio_1k = _episodio(delta_w=1000.0, duracion_s=3600.0, delta_q=30.0)
    diag_1k = ClasificadorCargasReglasService.clasificar_episodio(episodio_1k)

    assert diag_1k.aparato_sugerido == "Caloventor"
    assert diag_1k.categoria == CategoriaCarga.CLIMATIZACION

    episodio_2k = _episodio(delta_w=2000.0, duracion_s=3600.0, delta_q=35.0)
    diag_2k = ClasificadorCargasReglasService.clasificar_episodio(episodio_2k)
    assert diag_2k.aparato_sugerido == "Caloventor"


# ------------------------------------------------------------- Iluminación y PC


def test_clasificar_pc_por_variabilidad_en_regimen():
    """PC: 150-350 W, electrónica, pero con fluctuaciones continuas de potencia (MAD > 12 W)."""
    episodio = _episodio(delta_w=220.0, duracion_s=7200.0, delta_q=45.0, dispersion_w=25.0)
    diag = ClasificadorCargasReglasService.clasificar_episodio(episodio)

    assert diag.aparato_sugerido == "Computadora / PC"
    assert diag.naturaleza_electrica == NaturalezaElectrica.ELECTRONICA
    assert diag.confianza >= 0.80


def test_clasificar_iluminacion_baja_potencia():
    """Iluminación: < 90 W, potencia muy estable/plana, electrónica."""
    episodio = _episodio(delta_w=65.0, duracion_s=10800.0, delta_q=20.0, dispersion_w=2.0)
    diag = ClasificadorCargasReglasService.clasificar_episodio(episodio)

    assert diag.aparato_sugerido == "Iluminación"
    assert diag.categoria == CategoriaCarga.ILUMINACION
    assert diag.naturaleza_electrica == NaturalezaElectrica.ELECTRONICA


# ------------------------------------------------------------- Catálogo de Presets


def test_catalogo_presets_cargas_domesticas():
    """El catálogo de presets genera todas las cargas tipificadas con firmas válidas."""
    cargas = CatalogoPresetsCargas.obtener_todas("dev-test-1")
    nombres = {c.nombre for c in cargas}

    assert "Heladera" in nombres
    assert "Freezer" in nombres
    assert "Pava eléctrica" in nombres
    assert "Termotanque eléctrico" in nombres
    assert "Anafe eléctrico" in nombres
    assert "Horno eléctrico" in nombres
    assert "Caloventor" in nombres
    assert "Computadora / PC" in nombres
    assert "Iluminación" in nombres

    for carga in cargas:
        assert carga.firma is not None
        assert carga.firma.potencia_w > 0
        assert carga.firma.duracion_encendido_s is not None
        assert carga.firma.esta_completa is True


def test_clasificar_motor_industrial_alta_potencia():
    """Motor trifásico de 11 kW al 75% (8.25 kW) con reactiva inductiva."""
    episodio = _episodio(delta_w=8250.0, duracion_s=3600.0, delta_q=5500.0, factor_potencia=0.83)
    diag = ClasificadorCargasReglasService.clasificar_episodio(episodio)

    assert diag.categoria == CategoriaCarga.FUERZA_MOTRIZ
    assert diag.naturaleza_electrica == NaturalezaElectrica.MOTOR
    assert "Fuerza Motriz / Motor Industrial" in diag.aparato_sugerido
    assert diag.confianza >= 0.85


def test_clasificar_horno_industrial_resistivo():
    """Horno industrial de 45 kW con factor de potencia unitario y ciclo largo."""
    episodio = _episodio(delta_w=45000.0, duracion_s=7200.0, delta_q=50.0, factor_potencia=0.99)
    diag = ClasificadorCargasReglasService.clasificar_episodio(episodio)

    assert diag.categoria == CategoriaCarga.OTROS
    assert diag.naturaleza_electrica == NaturalezaElectrica.RESISTIVA
    assert "Horno / Calefactor Resistivo Industrial" in diag.aparato_sugerido
    assert diag.confianza >= 0.88


def test_clasificar_omite_heuristicas_domesticas_en_contexto_industrial():
    """En ámbito industrial, no se confunden motores de planta con heladeras ni resistencias con pavas o caloventores."""
    # 1. Pequeño motor o actuador (150 W, típico de heladera en el hogar)
    episodio_motor_chico = _episodio(delta_w=150.0, duracion_s=1200.0, delta_q=80.0)
    diag_ind_motor = ClasificadorCargasReglasService.clasificar_episodio(episodio_motor_chico, es_industrial=True)

    assert diag_ind_motor.categoria == CategoriaCarga.FUERZA_MOTRIZ
    assert diag_ind_motor.aparato_sugerido == "Fuerza Motriz / Motor"
    assert "Heladera" not in diag_ind_motor.aparato_sugerido

    # 2. Resistencia de 2000 W (en hogar sería Caloventor o Pava)
    episodio_caloventor = _episodio(delta_w=2000.0, duracion_s=3600.0, delta_q=35.0)
    diag_ind_resistivo = ClasificadorCargasReglasService.clasificar_episodio(episodio_caloventor, es_industrial=True)

    assert diag_ind_resistivo.categoria == CategoriaCarga.OTROS
    assert diag_ind_resistivo.aparato_sugerido == "Carga de proceso no clasificada"
    assert "Caloventor" not in diag_ind_resistivo.aparato_sugerido

    # 3. Consumo electrónico con fluctuaciones (en hogar sería PC)
    episodio_pc = _episodio(delta_w=220.0, duracion_s=7200.0, delta_q=45.0, dispersion_w=25.0)
    diag_ind_pc = ClasificadorCargasReglasService.clasificar_episodio(episodio_pc, es_industrial=True)

    assert diag_ind_pc.aparato_sugerido == "Carga de proceso no clasificada"
    assert "Computadora" not in diag_ind_pc.aparato_sugerido
