"""Calibración de firmas a partir de campañas de caracterización."""

from datetime import datetime, timedelta, timezone

from src.domain.cargas.servicios.calibrador_firma import CalibradorFirmaService
from src.domain.cargas.value_objects import (
    EstadoCampana,
    MotivoDescarte,
    MuestraCampana,
    OrigenFirma,
    TipoCampana,
)

INICIO = datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc)
CADENCIA = 1.0


def _muestras(potencias: list[float], reactivas: list[float] | None = None) -> list[MuestraCampana]:
    return [
        MuestraCampana(
            momento=INICIO + timedelta(seconds=i * CADENCIA),
            potencia_w=p,
            potencia_reactiva_var=reactivas[i] if reactivas else None,
        )
        for i, p in enumerate(potencias)
    ]


def _campana_pava(base: float = 140.0, potencia: float = 1850.0) -> list[float]:
    """Pre-roll de 70 s con la casa de fondo, arranque, y 180 s hirviendo."""
    return [base] * 70 + [base + potencia * 1.05] * 4 + [base + potencia] * 176 + [base] * 20


def test_pocas_muestras_no_producen_firma():
    """Si el medidor no entró en ráfaga, la campaña no sirve y hay que decirlo."""
    resultado = CalibradorFirmaService.calibrar(_muestras([140.0] * 5), TipoCampana.ACTIVA)

    assert resultado.estado == EstadoCampana.CONTAMINADA
    assert resultado.motivo == MotivoDescarte.SIN_MUESTRAS
    assert resultado.firma is None


def test_la_firma_se_mide_por_diferencia_contra_la_linea_de_base():
    """Sin restar el fondo, la firma de la pava incluiría a la heladera."""
    resultado = CalibradorFirmaService.calibrar(_muestras(_campana_pava()), TipoCampana.ACTIVA)

    assert resultado.estado == EstadoCampana.COMPLETADA
    assert resultado.linea_base_w == 140.0
    assert resultado.firma is not None
    assert resultado.firma.potencia_w == 1850.0
    assert resultado.firma.origen == OrigenFirma.CAMPANA


def test_la_firma_captura_la_duracion_no_solo_la_potencia():
    """La duración es lo único que separa una pava de un termotanque de la misma potencia."""
    resultado = CalibradorFirmaService.calibrar(_muestras(_campana_pava()), TipoCampana.ACTIVA)

    assert resultado.firma is not None
    assert resultado.firma.duracion_encendido_s == 180.0
    assert resultado.firma.esta_completa is True


def test_el_pico_de_arranque_se_guarda_pero_no_ensucia_la_potencia_de_regimen():
    """Un motor arranca a 6-8x su nominal: en la mediana de régimen sería veneno."""
    resultado = CalibradorFirmaService.calibrar(_muestras(_campana_pava()), TipoCampana.ACTIVA)

    assert resultado.firma is not None
    assert resultado.firma.pico_arranque_w == 1942.5
    assert resultado.firma.potencia_w == 1850.0


def test_una_carga_resistiva_se_reconoce_por_su_factor_de_potencia():
    potencias = _campana_pava()
    reactivas = [5.0] * len(potencias)

    resultado = CalibradorFirmaService.calibrar(_muestras(potencias, reactivas), TipoCampana.ACTIVA)

    assert resultado.firma is not None
    assert resultado.firma.factor_potencia is not None
    assert resultado.firma.factor_potencia > 0.99
    assert resultado.firma.es_resistiva is True


def test_una_carga_con_motor_se_distingue_por_su_reactiva():
    """Es el eje que después separa refrigeración de los resistivos en la serie gruesa."""
    potencias = [40.0] * 70 + [160.0] * 200
    reactivas = [10.0] * 70 + [130.0] * 200

    resultado = CalibradorFirmaService.calibrar(_muestras(potencias, reactivas), TipoCampana.ACTIVA)

    assert resultado.firma is not None
    assert resultado.firma.potencia_w == 120.0
    assert resultado.firma.potencia_reactiva_var == 120.0
    assert resultado.firma.es_resistiva is False


def test_si_nunca_se_prendio_nada_la_campana_lo_dice_en_castellano():
    resultado = CalibradorFirmaService.calibrar(_muestras([140.0] * 200), TipoCampana.ACTIVA)

    assert resultado.motivo == MotivoDescarte.SIN_ENCENDIDO_DETECTADO
    assert resultado.firma is None
    assert resultado.detalle is not None
    assert "prendió el aparato" in resultado.detalle


def test_si_entra_otra_carga_en_el_medio_la_campana_sale_contaminada():
    """No se emite una firma sucia con una advertencia al lado: la advertencia se pierde."""
    potencias = [140.0] * 70 + [1990.0] * 90 + [3990.0] * 90

    resultado = CalibradorFirmaService.calibrar(_muestras(potencias), TipoCampana.ACTIVA)

    assert resultado.estado == EstadoCampana.CONTAMINADA
    assert resultado.motivo in (MotivoDescarte.DISPERSION_EXCESIVA, MotivoDescarte.ESCALON_AJENO)
    assert resultado.firma is None


def test_un_escalon_ajeno_pequeno_pero_neto_tambien_contamina():
    potencias = [140.0] * 70 + [1990.0] * 100 + [2290.0] * 10 + [1990.0] * 90

    resultado = CalibradorFirmaService.calibrar(_muestras(potencias), TipoCampana.ACTIVA)

    assert resultado.estado == EstadoCampana.CONTAMINADA
    assert resultado.motivo == MotivoDescarte.ESCALON_AJENO
    assert resultado.detalle is not None
    assert "otra carga" in resultado.detalle


def test_campana_pasiva_de_heladera_mide_potencia_y_ambos_periodos():
    """La heladera no se prende a voluntad: se observa y se deja que el termostato cicle."""
    potencias: list[float] = [30.0] * 60
    for _ in range(6):
        potencias += [150.0] * 120 + [30.0] * 180

    resultado = CalibradorFirmaService.calibrar(_muestras(potencias), TipoCampana.PASIVA)

    assert resultado.estado == EstadoCampana.COMPLETADA
    assert resultado.firma is not None
    assert resultado.firma.potencia_w == 120.0
    assert resultado.firma.duracion_encendido_s == 120.0
    assert resultado.firma.duracion_apagado_s == 181.0


def test_una_pasiva_demasiado_corta_no_afirma_un_periodo_tipico():
    """Con un ciclo no hay "típico": la ventana fue corta y corresponde repetirla."""
    potencias = [30.0] * 60 + [150.0] * 120 + [30.0] * 60

    resultado = CalibradorFirmaService.calibrar(_muestras(potencias), TipoCampana.PASIVA)

    assert resultado.estado == EstadoCampana.CONTAMINADA
    assert resultado.motivo == MotivoDescarte.CICLOS_INSUFICIENTES
    assert resultado.detalle is not None
    assert "ventana fue corta" in resultado.detalle
