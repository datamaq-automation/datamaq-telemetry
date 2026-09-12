"""tests/unit/test_cargas_atribucion.py — Detección de episodios, desambiguación de firmas y reparto de consumo."""

from datetime import datetime, timedelta, timezone

from src.domain.cargas.entities import Carga, IntervaloActividadCarga
from src.domain.cargas.servicios.atribuidor_consumo import AtribuidorConsumoService
from src.domain.cargas.servicios.detector_escalones import DetectorEscalonesService
from src.domain.cargas.servicios.emparejador_firmas import EmparejadorFirmasService
from src.domain.cargas.value_objects import (
    EpisodioCarga,
    FirmaCarga,
    NaturalezaElectrica,
    OrigenClasificacionCarga,
    OrigenFirma,
)
from src.domain.telemetria.value_objects import LecturaPotenciaTemporal

INICIO = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
MEDIDOR = "dev-casa"


def _serie(muestras: list[tuple[float, float]], cadencia: float = 300.0) -> list[LecturaPotenciaTemporal]:
    return [
        LecturaPotenciaTemporal(momento=INICIO + timedelta(seconds=i * cadencia), potencia_w=p, potencia_reactiva_var=q)
        for i, (p, q) in enumerate(muestras)
    ]


def _plano(p: float, q: float, n: int) -> list[tuple[float, float]]:
    return [(p, q)] * n


# --------------------------------------------------------------- detección de escalones


def test_una_serie_plana_no_produce_escalones():
    assert DetectorEscalonesService.detectar(_serie(_plano(120.0, 90.0, 40))) == []


def test_un_escalon_neto_se_detecta_con_su_delta_reactiva():
    """El par (ΔP, ΔQ) es el espacio de firmas: hay que capturar los dos."""
    serie = _serie(_plano(120.0, 90.0, 15) + _plano(1970.0, 102.0, 15) + _plano(120.0, 90.0, 15))

    escalones = DetectorEscalonesService.detectar(serie)

    assert len(escalones) == 2
    assert escalones[0].delta_w == 1850.0
    assert escalones[0].delta_reactiva_var == 12.0
    assert escalones[0].es_encendido is True
    assert escalones[1].es_encendido is False


def test_el_umbral_se_calibra_del_ruido_de_la_propia_serie():
    """La misma constante fija sería ciega en un tablero de 200 kW."""
    domestica = _serie([(100.0 + (i % 3) * 5, 80.0) for i in range(60)])
    industrial = _serie([(100_000.0 + (i % 3) * 5_000, 80.0) for i in range(60)])

    assert DetectorEscalonesService.umbral_escalon(domestica) < 100.0
    assert DetectorEscalonesService.umbral_escalon(industrial) > 10_000.0


def test_un_hueco_de_datos_no_se_lee_como_escalon():
    """Tras una caída del medidor, la primera lectura no es una carga que entró."""
    antes = _serie(_plano(120.0, 90.0, 20))
    despues = [
        LecturaPotenciaTemporal(
            momento=antes[-1].momento + timedelta(hours=8) + timedelta(seconds=i * 300),
            potencia_w=2000.0,
            potencia_reactiva_var=90.0,
        )
        for i in range(20)
    ]

    escalones = DetectorEscalonesService.detectar(antes + despues)

    assert escalones == []


def test_un_encendido_se_empareja_con_su_apagado_en_un_episodio():
    serie = _serie(_plano(120.0, 90.0, 15) + _plano(1970.0, 102.0, 12) + _plano(120.0, 90.0, 15))

    episodios = DetectorEscalonesService.detectar_episodios(serie)

    assert len(episodios) == 1
    assert episodios[0].delta_w == 1850.0
    assert episodios[0].duracion_s == 3600.0
    assert episodios[0].ratio_reactiva is not None
    assert episodios[0].ratio_reactiva < 0.05


def test_un_encendido_sin_apagado_no_llega_a_episodio():
    """Sin cierre no se sabe cuánto duró, y la duración es la mitad de la identidad."""
    serie = _serie(_plano(120.0, 90.0, 15) + _plano(1970.0, 102.0, 15))

    assert DetectorEscalonesService.detectar_episodios(serie) == []


def test_cargas_anidadas_se_emparejan_respetando_el_orden_de_entrada():
    serie = _serie(
        _plano(120.0, 90.0, 10)
        + _plano(1970.0, 102.0, 6)
        + _plano(3970.0, 114.0, 6)
        + _plano(1970.0, 102.0, 6)
        + _plano(120.0, 90.0, 10)
    )

    episodios = DetectorEscalonesService.detectar_episodios(serie)

    assert len(episodios) == 2
    interno = min(episodios, key=lambda e: e.duracion_s)
    externo = max(episodios, key=lambda e: e.duracion_s)
    assert interno.inicio > externo.inicio
    assert interno.fin < externo.fin


def test_un_encendido_sin_apagado_no_se_aparea_con_el_de_otra_carga_horas_despues():
    """Sin este tope, un apagado perdido genera episodios de días con potencia absurda."""
    serie = _serie(
        _plano(120.0, 90.0, 5)
        + _plano(1970.0, 102.0, 5)  # entra una carga y su apagado se pierde bajo el umbral
        + [(1970.0 - i * 3, 102.0) for i in range(120)]  # deriva lenta, sin escalón
        + _plano(120.0, 90.0, 5)
    )

    episodios = DetectorEscalonesService.detectar_episodios(serie)

    assert all(e.duracion_s <= DetectorEscalonesService.DURACION_MAXIMA_EPISODIO_S for e in episodios)


def test_ningun_episodio_tiene_potencia_media_negativa():
    """Una carga no consume potencia negativa: ese par no describe un encendido real."""
    serie = _serie(
        _plano(3000.0, 120.0, 8)
        + _plano(4000.0, 130.0, 4)
        + _plano(500.0, 60.0, 20)
        + _plano(1400.0, 80.0, 8)
        + _plano(300.0, 50.0, 10)
    )

    episodios = DetectorEscalonesService.detectar_episodios(serie)

    assert all(e.potencia_media_w > 0 for e in episodios)
    assert all(e.energia_kwh >= 0 for e in episodios)


# ------------------------------------------------------- desambiguación de firmas


def _carga(nombre: str, potencia: float, duracion: float, fp: float, natural: NaturalezaElectrica) -> Carga:
    return Carga(
        id=f"carga-{nombre}",
        dispositivo_id=MEDIDOR,
        nombre=nombre,
        naturaleza_electrica=natural,
        firma=FirmaCarga(
            potencia_w=potencia,
            dispersion_w=potencia * 0.05,
            factor_potencia=fp,
            duracion_encendido_s=duracion,
            origen=OrigenFirma.CAMPANA,
        ),
    )


def _catalogo() -> list[Carga]:
    """Los cuatro resistivos son casi iguales en potencia: solo los separa la duración."""
    return [
        _carga("Pava eléctrica", 1850.0, 180.0, 0.99, NaturalezaElectrica.RESISTIVA),
        _carga("Anafe eléctrico", 1700.0, 900.0, 0.99, NaturalezaElectrica.RESISTIVA),
        _carga("Termotanque", 1800.0, 2400.0, 0.99, NaturalezaElectrica.RESISTIVA),
        _carga("Horno eléctrico", 1900.0, 4500.0, 0.99, NaturalezaElectrica.RESISTIVA),
        _carga("Heladera", 120.0, 1500.0, 0.72, NaturalezaElectrica.MOTOR),
    ]


def _episodio(delta_w: float, duracion_s: float, delta_q: float | None) -> EpisodioCarga:
    return EpisodioCarga(
        inicio=INICIO,
        fin=INICIO + timedelta(seconds=duracion_s),
        delta_w=delta_w,
        delta_reactiva_var=delta_q,
        duracion_s=duracion_s,
        potencia_media_w=delta_w,
        muestras=int(duracion_s / 300) or 1,
    )


def test_la_duracion_separa_al_termotanque_del_horno():
    """Misma potencia, mismo factor de potencia: solo difieren en cuánto duran."""
    decision = EmparejadorFirmasService.decidir(_episodio(1820.0, 2400.0, 15.0), _catalogo())

    assert decision.carga_id == "carga-Termotanque"


def test_la_misma_potencia_con_otra_duracion_va_a_otra_carga():
    decision = EmparejadorFirmasService.decidir(_episodio(1850.0, 4500.0, 15.0), _catalogo())

    assert decision.carga_id == "carga-Horno eléctrico"


def test_la_reactiva_separa_familias_enteras():
    """Una heladera y un resistivo de la misma potencia nunca deberían confundirse."""
    motor = EmparejadorFirmasService.decidir(_episodio(120.0, 1500.0, 115.0), _catalogo())

    assert motor.carga_id == "carga-Heladera"


def test_un_episodio_que_no_se_parece_a_nada_queda_sin_atribuir():
    decision = EmparejadorFirmasService.decidir(_episodio(8000.0, 600.0, 20.0), _catalogo())

    assert decision.carga_id is None
    assert "no alcanza el mínimo" in decision.motivo


def test_ante_dos_candidatos_igual_de_buenos_no_se_atribuye():
    """Preferir no atribuir antes que atribuir mal: una etiqueta falsa envenena el dataset."""
    catalogo = [
        _carga("Termotanque", 1800.0, 2400.0, 0.99, NaturalezaElectrica.RESISTIVA),
        _carga("Termotanque 2", 1800.0, 2400.0, 0.99, NaturalezaElectrica.RESISTIVA),
    ]

    decision = EmparejadorFirmasService.decidir(_episodio(1800.0, 2400.0, 10.0), catalogo)

    assert decision.carga_id is None
    assert "Ambiguo" in decision.motivo
    assert len(decision.candidatos) == 2


def test_sin_firmas_calibradas_no_se_atribuye_nada():
    sin_firma = [Carga(id="c1", dispositivo_id=MEDIDOR, nombre="Pava eléctrica", potencia_nominal_w=2000.0)]

    decision = EmparejadorFirmasService.decidir(_episodio(1850.0, 180.0, 10.0), sin_firma)

    assert decision.carga_id is None
    assert "firma calibrada" in decision.motivo


def test_una_carga_dada_de_baja_no_recibe_atribuciones():
    catalogo = _catalogo()
    catalogo[2].activa = False

    decision = EmparejadorFirmasService.decidir(_episodio(1820.0, 2400.0, 15.0), catalogo)

    assert decision.carga_id != "carga-Termotanque"


def test_sin_reactiva_medida_el_factor_no_premia_ni_castiga():
    """Un factor que no se puede evaluar vale 1: inventar un valor sería afirmar algo no medido."""
    con_q = EmparejadorFirmasService.puntuar(_episodio(1820.0, 2400.0, 10.0), _catalogo())
    sin_q = EmparejadorFirmasService.puntuar(_episodio(1820.0, 2400.0, None), _catalogo())

    assert con_q[0].carga_id == sin_q[0].carga_id
    assert sin_q[0].factor_reactiva_score == 1.0


# ----------------------------------------------------------------- atribución de kWh


def _intervalo(carga_id: str | None, potencia: float, minutos: float, confianza: float = 0.8):
    return IntervaloActividadCarga(
        id=None,
        dispositivo_id=MEDIDOR,
        carga_id=carga_id,
        inicio_at=INICIO,
        fin_at=INICIO + timedelta(minutes=minutos),
        potencia_media_w=potencia,
        energia_kwh=round(potencia * minutos * 60 / 3_600_000, 6),
        confianza=confianza,
    )


def test_el_residual_es_la_diferencia_contra_el_contador_no_un_ajuste():
    intervalos = [_intervalo("carga-Termotanque", 1800.0, 40), _intervalo("carga-Heladera", 120.0, 600)]

    atribucion = AtribuidorConsumoService.atribuir(
        INICIO, INICIO + timedelta(days=1), intervalos, _catalogo(), energia_total_kwh=5.0
    )

    assert atribucion.energia_atribuida_kwh == 2.4
    assert atribucion.residual_kwh == 2.6
    assert atribucion.residual_porcentaje == 0.52


def test_un_residual_alto_se_reporta_como_diagnostico_y_no_se_fuerza_el_cuadre():
    """A 5 min la pava y la iluminación caen ahí por diseño: es información, no un error."""
    atribucion = AtribuidorConsumoService.atribuir(
        INICIO, INICIO + timedelta(days=1), [_intervalo("carga-Heladera", 120.0, 600)], _catalogo(), 10.0
    )

    assert atribucion.calidad_suficiente is False
    assert atribucion.advertencia is not None
    assert "sin atribuir" in atribucion.advertencia


def test_atribuir_mas_que_el_total_medido_se_denuncia_en_vez_de_repartirse():
    """Un balance que siempre cierra no informa nada."""
    atribucion = AtribuidorConsumoService.atribuir(
        INICIO, INICIO + timedelta(days=1), [_intervalo("carga-Termotanque", 1800.0, 600)], _catalogo(), 5.0
    )

    assert atribucion.residual_kwh is not None
    assert atribucion.residual_kwh < 0
    assert atribucion.advertencia is not None
    assert "dos veces" in atribucion.advertencia


def test_sin_lecturas_del_contador_no_se_finge_un_total():
    atribucion = AtribuidorConsumoService.atribuir(
        INICIO, INICIO + timedelta(days=1), [_intervalo("carga-Heladera", 120.0, 600)], _catalogo(), None
    )

    assert atribucion.residual_kwh is None
    assert atribucion.calidad_suficiente is False
    assert atribucion.advertencia is not None
    assert "no se puede cerrar el balance" in atribucion.advertencia


def test_los_intervalos_no_atribuidos_aparecen_con_nombre_propio():
    intervalos = [_intervalo("carga-Heladera", 120.0, 600), _intervalo(None, 2000.0, 30)]

    atribucion = AtribuidorConsumoService.atribuir(INICIO, INICIO + timedelta(days=1), intervalos, _catalogo(), 3.0)

    no_atribuido = [i for i in atribucion.items if i.carga_id is None]
    assert no_atribuido
    assert all(i.nombre == "No atribuido" for i in no_atribuido)


def test_una_correccion_humana_se_marca_y_lleva_confianza_plena():
    intervalo = _intervalo(None, 2000.0, 3)

    intervalo.corregir("carga-Pava eléctrica", usuario_id="u1", notas="fui yo, herví agua")

    assert intervalo.carga_id == "carga-Pava eléctrica"
    assert intervalo.origen == OrigenClasificacionCarga.CORRECCION_HUMANA
    assert intervalo.es_correccion_humana is True
    assert intervalo.confianza == 1.0
    assert intervalo.corregido_at is not None


def test_el_reporte_tiene_una_sola_fila_de_no_atribuido():
    """El residual del balance y los episodios sin imputar son lo mismo para quien lee."""
    intervalos = [_intervalo("carga-Heladera", 120.0, 600), _intervalo(None, 2000.0, 30)]

    atribucion = AtribuidorConsumoService.atribuir(INICIO, INICIO + timedelta(days=1), intervalos, _catalogo(), 5.0)

    filas_sin_atribuir = [i for i in atribucion.items if i.carga_id is None]
    assert len(filas_sin_atribuir) == 1


def test_los_porcentajes_suman_cien_contra_el_consumo_real():
    """Con denominadores distintos por item el reporte dejaba de ser interpretable."""
    intervalos = [
        _intervalo("carga-Termotanque", 1800.0, 40),
        _intervalo("carga-Heladera", 120.0, 600),
        _intervalo(None, 2000.0, 30),
    ]

    atribucion = AtribuidorConsumoService.atribuir(INICIO, INICIO + timedelta(days=1), intervalos, _catalogo(), 5.0)

    assert abs(sum(i.porcentaje for i in atribucion.items) - 1.0) < 0.001


def test_el_residual_se_suma_a_los_episodios_sin_imputar_no_los_reemplaza():
    intervalos = [_intervalo(None, 2000.0, 30)]

    atribucion = AtribuidorConsumoService.atribuir(INICIO, INICIO + timedelta(days=1), intervalos, _catalogo(), 5.0)

    sin_atribuir = next(i for i in atribucion.items if i.carga_id is None)
    assert sin_atribuir.energia_kwh == 5.0
    assert sin_atribuir.intervalos == 1
