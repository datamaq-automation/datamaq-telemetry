"""Penalización por exceso de potencia con tarifa de distribuidora verificada (Edesur T3 MT, 2025-07).

Fixture: factura real "Cristal Avellaneda - EDESUR/2025-07.pdf", LSP A 9904-02469153 17.
Renglones: Cap.Sum.Conv T3 848,40 kW = 3.521.212,94; adquirida 930,00 kW;
Recargo Exceso Potencia T3 122,40 kW = 508.010,91.
"""

from decimal import Decimal

from src.domain.telemetria.tarifas_distribuidora import (
    calcular_recargo_exceso_potencia,
    obtener_tarifa_capacidad,
)

CSC_KW = Decimal("848.40")
ADQUIRIDA_KW = Decimal("930.00")


def test_tarifa_edesur_2025_07_tiene_fuente_y_vigencia():
    tarifa = obtener_tarifa_capacidad("Edesur", "2025-07")

    assert tarifa is not None
    assert tarifa.tarifa == "T3 MT"
    assert tarifa.fuente_archivo == "Cristal Avellaneda - EDESUR/2025-07.pdf"
    assert tarifa.vigencia_desde == "2025-07-01"


def test_valor_unitario_ponderado_coincide_con_la_factura():
    tarifa = obtener_tarifa_capacidad("Edesur", "2025-07")

    # (6 x 4127,92 + 24 x 4156,04) / 30 = 4150,416
    assert tarifa is not None
    assert round(tarifa.valor_unitario_ars_kw, 3) == Decimal("4150.416")


def test_recargo_exceso_2025_07_coincide_con_la_factura():
    tarifa = obtener_tarifa_capacidad("Edesur", "2025-07")

    recargo = calcular_recargo_exceso_potencia(CSC_KW, ADQUIRIDA_KW, tarifa)

    assert recargo is not None
    assert recargo.exceso_kw == Decimal("81.60")
    # La factura dice 508.010,91; con el valor unitario ponderado sale 508.010,92. La diferencia de
    # un centavo viene del redondeo interno de la distribuidora, que no se puede reconstruir desde
    # los importes impresos. Por eso se tolera un centavo y no se fuerza el redondeo.
    assert abs(recargo.importe_ars - Decimal("508010.91")) <= Decimal("0.01")
    assert recargo.distribuidora == "Edesur"
    assert recargo.tarifa == "T3 MT"
    assert recargo.periodo == "2025-07"
    assert recargo.fuente_archivo == "Cristal Avellaneda - EDESUR/2025-07.pdf"


def test_sin_exceso_el_recargo_es_cero():
    tarifa = obtener_tarifa_capacidad("Edesur", "2025-07")

    recargo = calcular_recargo_exceso_potencia(CSC_KW, Decimal("800.00"), tarifa)

    assert recargo is not None
    assert recargo.exceso_kw == Decimal("0")
    assert recargo.importe_ars == Decimal("0.00")


def test_periodo_sin_tarifa_verificada_devuelve_none():
    assert obtener_tarifa_capacidad("Edesur", "2025-06") is None
    assert calcular_recargo_exceso_potencia(CSC_KW, ADQUIRIDA_KW, None) is None


def test_distribuidora_sin_tarifa_cargada_devuelve_none():
    # EDELAP no tiene precio verificado: la penalización queda sin calcular.
    assert obtener_tarifa_capacidad("EDELAP", "2024-08") is None
