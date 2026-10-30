"""tests/unit/test_penalizacion_periodo.py.

Penalización por período de facturación: solo períodos con factura y tarifa verificadas."""

from decimal import Decimal

from src.domain.telemetria.penalizacion_periodo import (
    CONCEPTO_REACTIVA,
    CONCEPTO_RECARGO_EXCESO,
    MOTIVO_PERIODO_SIN_TARIFA,
    calcular_penalizacion_periodo,
)

PLANTA_DURAX = "c64fd625-0037-4caa-b68a-800e8e0ee548"
PLANTA_UPP = "4f68f653-a604-4834-8154-31f938248572"


def test_durax_2025_07_expone_recargo_con_distribuidora_tarifa_y_fuente():
    penalizacion = calcular_penalizacion_periodo(PLANTA_DURAX, "2025-07")

    assert penalizacion.distribuidora == "Edesur"
    assert penalizacion.tarifa == "T3 MT"
    assert penalizacion.fuente_archivo == "Cristal Avellaneda - EDESUR/2025-07.pdf"
    assert penalizacion.concepto == CONCEPTO_RECARGO_EXCESO
    assert penalizacion.motivo_sin_precio is None
    assert penalizacion.importe_ars is not None
    # La factura dice 508.010,91; el cálculo sale 508.010,92 (centavo de redondeo de la distribuidora).
    assert abs(penalizacion.importe_ars - Decimal("508010.91")) <= Decimal("0.01")


def test_edelap_2024_08_tg_fi_bajo_limite_da_cero_con_distribuidora_y_tarifa():
    penalizacion = calcular_penalizacion_periodo(PLANTA_UPP, "2024-08")

    assert penalizacion.importe_ars == Decimal("0.00")
    assert penalizacion.distribuidora == "EDELAP"
    assert penalizacion.tarifa == "T5M12"
    assert penalizacion.fuente_archivo == "Papelera platense - EDELAP/2024-08.pdf"
    assert penalizacion.concepto == CONCEPTO_REACTIVA
    assert penalizacion.motivo_sin_precio is None


def test_edelap_2023_12_tg_fi_bajo_limite_da_cero():
    penalizacion = calcular_penalizacion_periodo(PLANTA_UPP, "2023-12")

    assert penalizacion.importe_ars == Decimal("0.00")
    assert penalizacion.fuente_archivo == "Papelera platense - EDELAP/2023-12.pdf"


def test_periodo_sin_factura_verificada_no_da_cifra_y_motiva():
    penalizacion = calcular_penalizacion_periodo(PLANTA_DURAX, "2025-06")

    assert penalizacion.importe_ars is None
    assert penalizacion.motivo_sin_precio == MOTIVO_PERIODO_SIN_TARIFA
    assert penalizacion.distribuidora is None
    assert penalizacion.fuente_archivo is None


def test_planta_sin_facturas_verificadas_no_da_cifra():
    penalizacion = calcular_penalizacion_periodo("planta-desconocida", "2025-07")

    assert penalizacion.importe_ars is None
    assert penalizacion.motivo_sin_precio == MOTIVO_PERIODO_SIN_TARIFA
