"""Penalización por período de facturación, solo para períodos con factura y tarifa verificadas.

Regla (decisión del dueño 2026-10-14, brief de tarifas 1A/2A/3A): la cifra se expone por período
de facturación, nunca por ventana de análisis. Demanda y tg phi salen de la factura de ese período,
no de una estimación. Un período sin factura verificada devuelve motivo, sin importe.
"""

from dataclasses import dataclass
from decimal import Decimal

from src.domain.telemetria.tarifas_distribuidora import (
    calcular_penalizacion_reactiva_edelap,
    calcular_recargo_exceso_potencia,
    obtener_tarifa_capacidad,
)

MOTIVO_PERIODO_SIN_TARIFA = "período sin tarifa verificada"
CONCEPTO_RECARGO_EXCESO = "recargo por exceso de potencia (T3 MT)"
CONCEPTO_REACTIVA = "penalización por energía reactiva (régimen 1992)"


@dataclass(frozen=True)
class FacturaVerificada:
    """Datos de una factura real que se pudo verificar contra el PDF original."""

    planta_id: str
    distribuidora: str
    tarifa: str
    periodo: str
    fuente_archivo: str
    adquirida_kw: Decimal | None = None
    tg_fi_por_bloque: tuple[Decimal, ...] | None = None


# Papelera platense UPP (planta 4f68f653-...), EDELAP T5M12: tg phi de la factura, Tg. Fi. punta/valle/resto.
# Cristal Avellaneda / Durax (planta c64fd625-...), Edesur T3 MT: demanda adquirida de la factura.
_FACTURAS_VERIFICADAS: tuple[FacturaVerificada, ...] = (
    FacturaVerificada(
        planta_id="c64fd625-0037-4caa-b68a-800e8e0ee548",
        distribuidora="Edesur",
        tarifa="T3 MT",
        periodo="2025-07",
        fuente_archivo="Cristal Avellaneda - EDESUR/2025-07.pdf",
        adquirida_kw=Decimal("930.00"),
    ),
    FacturaVerificada(
        planta_id="4f68f653-a604-4834-8154-31f938248572",
        distribuidora="EDELAP",
        tarifa="T5M12",
        periodo="2024-08",
        fuente_archivo="Papelera platense - EDELAP/2024-08.pdf",
        tg_fi_por_bloque=(Decimal("0.431"), Decimal("0.438"), Decimal("0.426")),
    ),
    FacturaVerificada(
        planta_id="4f68f653-a604-4834-8154-31f938248572",
        distribuidora="EDELAP",
        tarifa="T5M12",
        periodo="2023-12",
        fuente_archivo="Papelera platense - EDELAP/2023-12.pdf",
        tg_fi_por_bloque=(Decimal("0.483"), Decimal("0.492"), Decimal("0.481")),
    ),
)


@dataclass(frozen=True)
class PenalizacionPeriodo:
    """Cifra de penalización de un período. importe_ars None = sin cifra, con motivo."""

    planta_id: str
    periodo: str
    distribuidora: str | None
    tarifa: str | None
    fuente_archivo: str | None
    concepto: str | None
    importe_ars: Decimal | None
    motivo_sin_precio: str | None


def _factura_verificada(planta_id: str, periodo: str) -> FacturaVerificada | None:
    for factura in _FACTURAS_VERIFICADAS:
        if factura.planta_id == planta_id and factura.periodo == periodo:
            return factura
    return None


def calcular_penalizacion_periodo(planta_id: str, periodo: str) -> PenalizacionPeriodo:
    """Penalización del período de facturación, con su distribuidora, tarifa y fuente."""
    factura = _factura_verificada(planta_id, periodo)
    if factura is None:
        return PenalizacionPeriodo(
            planta_id=planta_id,
            periodo=periodo,
            distribuidora=None,
            tarifa=None,
            fuente_archivo=None,
            concepto=None,
            importe_ars=None,
            motivo_sin_precio=MOTIVO_PERIODO_SIN_TARIFA,
        )

    if factura.distribuidora == "EDELAP" and factura.tg_fi_por_bloque is not None:
        reactiva = calcular_penalizacion_reactiva_edelap(
            periodo=periodo,
            fuente_archivo=factura.fuente_archivo,
            tg_fi_por_bloque=factura.tg_fi_por_bloque,
        )
        return PenalizacionPeriodo(
            planta_id=planta_id,
            periodo=periodo,
            distribuidora=factura.distribuidora,
            tarifa=factura.tarifa,
            fuente_archivo=factura.fuente_archivo,
            concepto=CONCEPTO_REACTIVA,
            importe_ars=reactiva.importe_ars,
            motivo_sin_precio=reactiva.motivo_sin_precio,
        )

    tarifa_capacidad = obtener_tarifa_capacidad(factura.distribuidora, periodo)
    if factura.adquirida_kw is not None and tarifa_capacidad is not None:
        recargo = calcular_recargo_exceso_potencia(tarifa_capacidad.csc_kw, factura.adquirida_kw, tarifa_capacidad)
        if recargo is not None:
            return PenalizacionPeriodo(
                planta_id=planta_id,
                periodo=periodo,
                distribuidora=factura.distribuidora,
                tarifa=factura.tarifa,
                fuente_archivo=factura.fuente_archivo,
                concepto=CONCEPTO_RECARGO_EXCESO,
                importe_ars=recargo.importe_ars,
                motivo_sin_precio=None,
            )

    return PenalizacionPeriodo(
        planta_id=planta_id,
        periodo=periodo,
        distribuidora=factura.distribuidora,
        tarifa=factura.tarifa,
        fuente_archivo=factura.fuente_archivo,
        concepto=None,
        importe_ars=None,
        motivo_sin_precio=MOTIVO_PERIODO_SIN_TARIFA,
    )
