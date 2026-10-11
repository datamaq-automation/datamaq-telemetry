"""tests/unit/test_costo_potencia_esquemas.py — M-2: costo de potencia por esquema tarifario.

Los importes de LIQUIDACIONES_EDESUR_DURAX son la transcripción de las 12 liquidaciones Edesur de Durax (repo
datamaq-data, método transcripcion_verificada, pendiente de cotejo D2). Viven acá como fixture del repo de código, nunca
como datos del YAML real. Los precios por kW se derivan de cada importe.
"""

import pytest

from src.domain.telemetria.servicios.costo_potencia import (
    DatosCapacidadUnica,
    DatosPotenciaPorFranja,
    FranjaPotencia,
    costo_potencia_capacidad_unica,
    costo_potencia_por_franja,
)

LIQUIDACIONES_EDESUR_DURAX = [
    ("2024-08", 848.4, 655.2, 2483698.66, 1755526.18, 0.0),
    ("2024-09", 848.4, 680.4, 2558211.45, 1912608.57, 0.0),
    ("2024-10", 848.4, 740.4, 2630769.62, 2149333.81, 0.0),
    ("2024-11", 848.4, 985.2, 2767527.6, 2875089.46, 669373.71),
    ("2024-12", 848.4, 964.8, 2915490.96, 2815556.55, 600005.56),
    ("2025-01", 848.4, 991.2, 3034678.09, 2892599.14, 766181.11),
    ("2025-02", 848.4, 950.4, 3156064.42, 4409592.34, 569162.96),
    ("2025-03", 848.4, 934.8, 3183714.32, 4909565.59, 486338.25),
    ("2025-04", 848.4, 970.8, 3269988.4, 5116465.49, 707649.54),
    ("2025-05", 848.4, 963.6, 3374229.34, 5989806.98, 687254.63),
    ("2025-06", 848.4, 992.4, 3477711.2, 6477825.69, 885414.44),
    ("2025-07", 848.4, 930.0, 3521212.94, 6155158.5, 508010.91),
]

FACTOR = 1.5
LIMITE = 0.5
EXCEDENTE = 2.0


def _datos_mes(csc, adq, conv_ars, adq_ars):
    return DatosCapacidadUnica(
        csc_kw=csc,
        adquirida_kw=adq,
        precio_csc=conv_ars / csc,
        precio_adquirida=adq_ars / adq,
        factor_exceso=FACTOR,
        limite_fraccion_csc=LIMITE,
        factor_excedente=EXCEDENTE,
    )


@pytest.mark.parametrize(("periodo", "csc", "adq", "conv_ars", "adq_ars", "recargo_ars"), LIQUIDACIONES_EDESUR_DURAX)
def test_capacidad_unica_reproduce_el_total_de_cada_liquidacion(periodo, csc, adq, conv_ars, adq_ars, recargo_ars):
    total_liquidacion = conv_ars + adq_ars + recargo_ars
    calculado = costo_potencia_capacidad_unica(_datos_mes(csc, adq, conv_ars, adq_ars))
    assert calculado == pytest.approx(total_liquidacion, abs=0.05), periodo


def test_capacidad_unica_sin_exceso_no_cobra_recargo():
    datos = DatosCapacidadUnica(
        csc_kw=100,
        adquirida_kw=80,
        precio_csc=10,
        precio_adquirida=5,
        factor_exceso=FACTOR,
        limite_fraccion_csc=LIMITE,
        factor_excedente=EXCEDENTE,
    )
    assert costo_potencia_capacidad_unica(datos) == pytest.approx(100 * 10 + 80 * 5)


def test_capacidad_unica_recargo_pasa_al_factor_excedente_sobre_la_mitad_de_la_csc():
    # exceso 80 con CSC 100: 50 a 1,5 y 30 a 2,0 (el límite es 0,5 x CSC). Precio CSC 1, adquirida sin precio.
    datos = DatosCapacidadUnica(
        csc_kw=100,
        adquirida_kw=180,
        precio_csc=1,
        precio_adquirida=0,
        factor_exceso=FACTOR,
        limite_fraccion_csc=LIMITE,
        factor_excedente=EXCEDENTE,
    )
    assert costo_potencia_capacidad_unica(datos) == pytest.approx(100 + 1.5 * 50 + 2.0 * 30)


def test_capacidad_unica_csc_de_la_spec_848_4_por_3752_61():
    # Spec: CSC 848,4 x 3.752,61 = 3.183.714,32 (mar-25, sin exceso).
    datos = DatosCapacidadUnica(
        csc_kw=848.4,
        adquirida_kw=848.4,
        precio_csc=3752.61,
        precio_adquirida=0,
        factor_exceso=FACTOR,
        limite_fraccion_csc=LIMITE,
        factor_excedente=EXCEDENTE,
    )
    assert costo_potencia_capacidad_unica(datos) == pytest.approx(3183714.32, abs=0.01)


def test_capacidad_unica_solo_usa_la_csc_no_franjas_de_la_acometida():
    # DatosCapacidadUnica no tiene campos de punta ni fuera de punta: no hay forma de contarlas dos veces.
    campos = set(DatosCapacidadUnica.__dataclass_fields__)
    assert not any("punta" in c for c in campos)


def test_capacidad_unica_rechaza_csc_cero_y_negativos():
    with pytest.raises(ValueError, match="mayor que cero"):
        costo_potencia_capacidad_unica(
            DatosCapacidadUnica(
                csc_kw=0,
                adquirida_kw=0,
                precio_csc=1,
                precio_adquirida=1,
                factor_exceso=FACTOR,
                limite_fraccion_csc=LIMITE,
                factor_excedente=EXCEDENTE,
            )
        )
    with pytest.raises(ValueError, match="no pueden ser negativos"):
        costo_potencia_capacidad_unica(
            DatosCapacidadUnica(
                csc_kw=10,
                adquirida_kw=-1,
                precio_csc=1,
                precio_adquirida=1,
                factor_exceso=FACTOR,
                limite_fraccion_csc=LIMITE,
                factor_excedente=EXCEDENTE,
            )
        )


def test_por_franja_paga_cada_franja_contra_su_contratada():
    # Punta: 800 contratados, demanda 900 → 800*10 + 1,5*100*10 = 9.500. Fuera de punta: 850 contratados, demanda 800 → 4.250.
    datos = DatosPotenciaPorFranja(
        franjas=(
            FranjaPotencia(contratada_kw=800, demanda_kw=900, precio_por_kw=10),
            FranjaPotencia(contratada_kw=850, demanda_kw=800, precio_por_kw=5),
        ),
        factor_exceso=FACTOR,
    )
    assert costo_potencia_por_franja(datos) == pytest.approx(9500 + 4250)


def test_por_franja_rechaza_valores_negativos():
    datos = DatosPotenciaPorFranja(
        franjas=(FranjaPotencia(contratada_kw=-1, demanda_kw=10, precio_por_kw=1),),
        factor_exceso=FACTOR,
    )
    with pytest.raises(ValueError, match="no pueden ser negativos"):
        costo_potencia_por_franja(datos)
