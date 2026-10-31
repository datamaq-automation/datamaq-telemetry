"""src/domain/telemetria/penalizacion_periodo.py.

Penalización por período de facturación, solo para períodos con factura y tarifa verificadas.

Regla (decisión del dueño 2026-10-14, brief de tarifas 1A/2A/3A): la cifra se expone por período
de facturación, nunca por ventana de análisis. Demanda y tg phi salen de la factura de ese período,
no de una estimación. Un período sin factura verificada devuelve motivo, sin importe.

Desde datamaq#111 las facturas verificadas, las tarifas y los parámetros regulatorios salen del puerto
`RepositorioParametrosRegulatoriosPort`: este módulo no contiene datos de negocio.
"""

from dataclasses import dataclass
from decimal import Decimal

from src.domain.telemetria.parametros_regulatorios import RepositorioParametrosRegulatoriosPort
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


def calcular_penalizacion_periodo(
    repo: RepositorioParametrosRegulatoriosPort, planta_id: str, periodo: str
) -> PenalizacionPeriodo:
    """Penalización del período de facturación, con su distribuidora, tarifa y fuente."""
    factura = repo.obtener_factura_verificada(planta_id, periodo)
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
            limite_tg_fi=repo.limite_tg_fi_regimen_1992(factura.distribuidora, factura.tarifa),
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

    tarifa_capacidad = obtener_tarifa_capacidad(repo, factura.distribuidora, periodo)
    if factura.adquirida_kw is not None and tarifa_capacidad is not None:
        recargo = calcular_recargo_exceso_potencia(
            tarifa_capacidad.csc_kw,
            factura.adquirida_kw,
            tarifa_capacidad,
            factor_recargo=repo.factor_recargo_exceso(factura.distribuidora, factura.tarifa),
        )
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
