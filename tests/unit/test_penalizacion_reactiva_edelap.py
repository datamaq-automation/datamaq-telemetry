"""tests/unit/test_penalizacion_reactiva_edelap.py.

Penalización reactiva EDELAP T5M12 con el régimen 1992 (tg phi <= 0,62 => 0; mayor => sin precio).

Fixtures reales (Tg. Fi. por bloque, punta/valle/resto, de la factura):
- 2024-08 (EDELAP/2024-08.pdf, Nº 0020-01914132): 0,431 / 0,438 / 0,426 => sin cargo reactivo.
- 2023-12 (EDELAP/2023-12.pdf, Nº 0020-01719216): 0,483 / 0,492 / 0,481 => sin cargo reactivo.

Ninguna factura de data/ supera 0,62, así que el caso "sin precio" usa un valor sintético
(0,63) justo por encima del límite. No es una factura real.
"""

from decimal import Decimal

from src.domain.telemetria.tarifas_distribuidora import (
    LIMITE_TG_FI_REGIMEN_1992,
    MOTIVO_REACTIVA_NO_VERIFICADA,
    calcular_penalizacion_reactiva_edelap,
)


def test_factura_real_2024_08_tg_fi_bajo_limite_da_penalizacion_cero():
    penalizacion = calcular_penalizacion_reactiva_edelap(
        periodo="2024-08",
        fuente_archivo="Papelera platense - EDELAP/2024-08.pdf",
        tg_fi_por_bloque=(Decimal("0.431"), Decimal("0.438"), Decimal("0.426")),
    )

    assert penalizacion.importe_ars == Decimal("0.00")
    assert penalizacion.motivo_sin_precio is None
    assert penalizacion.distribuidora == "EDELAP"
    assert penalizacion.tarifa == "T5M12"
    assert penalizacion.periodo == "2024-08"
    assert penalizacion.fuente_archivo == "Papelera platense - EDELAP/2024-08.pdf"
    assert penalizacion.tg_fi_maximo == Decimal("0.438")


def test_factura_real_2023_12_tg_fi_bajo_limite_da_penalizacion_cero():
    penalizacion = calcular_penalizacion_reactiva_edelap(
        periodo="2023-12",
        fuente_archivo="Papelera platense - EDELAP/2023-12.pdf",
        tg_fi_por_bloque=(Decimal("0.483"), Decimal("0.492"), Decimal("0.481")),
    )

    assert penalizacion.importe_ars == Decimal("0.00")
    assert penalizacion.motivo_sin_precio is None


def test_tg_fi_superior_al_limite_queda_sin_precio_con_motivo():
    penalizacion = calcular_penalizacion_reactiva_edelap(
        periodo="2025-01",
        fuente_archivo="sintético (tg phi sobre el límite)",
        tg_fi_por_bloque=(Decimal("0.63"), Decimal("0.50"), Decimal("0.40")),
    )

    assert penalizacion.importe_ars is None
    assert penalizacion.motivo_sin_precio == MOTIVO_REACTIVA_NO_VERIFICADA
    assert penalizacion.motivo_sin_precio == "tarifa reactiva no verificada"


def test_tg_fi_exactamente_en_el_limite_cuenta_como_bajo_limite():
    assert LIMITE_TG_FI_REGIMEN_1992 == Decimal("0.62")

    penalizacion = calcular_penalizacion_reactiva_edelap(
        periodo="2025-01",
        fuente_archivo="sintético (en el límite)",
        tg_fi_por_bloque=(Decimal("0.62"),),
    )

    assert penalizacion.importe_ars == Decimal("0.00")
