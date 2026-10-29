"""Pruebas de aplicación del cálculo de corrección angular por fase de TI (issue #63).

Verifican que el servicio devuelve candidatos sin elegir uno y que no depende de persistencia.
"""

import math

import pytest

from src.application.services.correccion_angular_ti_app_service import (
    CalcularCorreccionAngularTIApplicationService,
    MedicionFaseTI,
)


def _medicion_para(phi_bruto_deg: float, alpha_deg: float, s: float = 1000.0) -> MedicionFaseTI:
    """Medición sintética: el medidor reporta P = S·cos(φ_almacenado), con φ_almacenado = φ_bruto - alfa."""
    phi_almacenado = phi_bruto_deg - alpha_deg
    p = s * math.cos(math.radians(phi_almacenado))
    return MedicionFaseTI(v=230.0, i=s / 230.0, p=p)


def test_candidato_unico_cuando_las_dos_correcciones_difieren():
    # Bruto real +40°. Antes alfa 0 → |φ|=40. Después alfa 10 → φ_almacenado=30, |φ|=30.
    servicio = CalcularCorreccionAngularTIApplicationService()

    resultado = servicio.candidatos_por_fase(
        antes={"R": _medicion_para(40.0, 0.0)},
        alpha_antes={"R": 0.0},
        despues={"R": _medicion_para(40.0, 10.0)},
        alpha_despues={"R": 10.0},
    )

    assert resultado["R"] == pytest.approx([40.0], abs=0.1)


def test_devuelve_ambos_signos_sin_elegir_cuando_las_dos_mediciones_son_simetricas():
    # Con alfa 0 en ambas, |φ|=40 deja +40° y -40° compatibles: el servicio debe devolver los dos.
    servicio = CalcularCorreccionAngularTIApplicationService()

    resultado = servicio.candidatos_por_fase(
        antes={"S": _medicion_para(40.0, 0.0)},
        alpha_antes={},
        despues={"S": _medicion_para(40.0, 0.0)},
        alpha_despues={},
    )

    assert resultado["S"] == pytest.approx([-40.0, 40.0], abs=0.1)


def test_fase_sin_coincidencia_devuelve_lista_vacia():
    # Antes |φ|=10 con alfa 0; después |φ|=90 con alfa 0. No hay bruto común dentro de la tolerancia.
    servicio = CalcularCorreccionAngularTIApplicationService()

    resultado = servicio.candidatos_por_fase(
        antes={"T": MedicionFaseTI(v=230.0, i=5.0, p=230.0 * 5.0 * math.cos(math.radians(10.0)))},
        alpha_antes={"T": 0.0},
        despues={"T": MedicionFaseTI(v=230.0, i=5.0, p=230.0 * 5.0 * math.cos(math.radians(90.0)))},
        alpha_despues={"T": 0.0},
    )

    assert resultado["T"] == []


def test_solo_procesa_fases_presentes_en_ambas_mediciones():
    servicio = CalcularCorreccionAngularTIApplicationService()

    resultado = servicio.candidatos_por_fase(
        antes={"R": _medicion_para(40.0, 0.0), "S": _medicion_para(40.0, 0.0)},
        alpha_antes={},
        despues={"R": _medicion_para(40.0, 0.0)},
        alpha_despues={},
    )

    assert set(resultado) == {"R"}


def test_fase_sin_alfa_declarada_usa_cero():
    servicio = CalcularCorreccionAngularTIApplicationService()

    sin_alfa = servicio.candidatos_por_fase(
        antes={"R": _medicion_para(40.0, 0.0)},
        alpha_antes={},
        despues={"R": _medicion_para(40.0, 0.0)},
        alpha_despues={},
    )
    con_alfa_cero = servicio.candidatos_por_fase(
        antes={"R": _medicion_para(40.0, 0.0)},
        alpha_antes={"R": 0.0},
        despues={"R": _medicion_para(40.0, 0.0)},
        alpha_despues={"R": 0.0},
    )

    assert sin_alfa == con_alfa_cero


def test_potencia_aparente_nula_propaga_error_de_dominio():
    servicio = CalcularCorreccionAngularTIApplicationService()

    with pytest.raises(ValueError):
        servicio.candidatos_por_fase(
            antes={"R": MedicionFaseTI(v=0.0, i=5.0, p=0.0)},
            alpha_antes={},
            despues={"R": _medicion_para(40.0, 0.0)},
            alpha_despues={},
        )
