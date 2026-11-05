"""src/adapters/gateways/in_memory_parametros_regulatorios.py.

Repositorio en memoria del puerto `RepositorioParametrosRegulatoriosPort` (datamaq#111). Lo usan los tests de
dominio y aplicación, sin base de datos, con la misma carga inicial que la migración.
"""

from decimal import Decimal

from src.adapters.gateways.parametros_regulatorios_iniciales import (
    FACTURAS_VERIFICADAS_INICIALES,
    PARAMETROS_REGULATORIOS_INICIALES,
    TARIFAS_CAPACIDAD_INICIALES,
)
from src.domain.telemetria.parametros_regulatorios import RepositorioParametrosRegulatoriosPort
from src.domain.telemetria.penalizacion_periodo import FacturaVerificada
from src.domain.telemetria.tarifas_distribuidora import TarifaCapacidad


def _tg(fila: dict[str, str | None]) -> tuple[Decimal, ...] | None:
    bloques = (fila["tg_fi_bloque_punta"], fila["tg_fi_bloque_valle"], fila["tg_fi_bloque_resto"])
    if all(b is None for b in bloques):
        return None
    return tuple(Decimal(b) for b in bloques if b is not None)


class RepositorioParametrosRegulatoriosEnMemoria(RepositorioParametrosRegulatoriosPort):
    """Mismos datos que la carga inicial de la base, sin I/O."""

    def __init__(self) -> None:
        self._tarifas = {
            (f["distribuidora"], f["periodo"]): TarifaCapacidad(
                distribuidora=f["distribuidora"],
                tarifa=f["tarifa"],
                periodo=f["periodo"],
                fuente_archivo=f["fuente_archivo"],
                vigencia_desde=f["vigencia_desde"],
                importe_capacidad_convenida_ars=Decimal(f["importe_capacidad_convenida_ars"]),
                csc_kw=Decimal(f["csc_kw"]),
            )
            for f in TARIFAS_CAPACIDAD_INICIALES
        }
        self._facturas = {
            (f["planta_id"], f["periodo"]): FacturaVerificada(
                planta_id=f["planta_id"],
                distribuidora=f["distribuidora"],
                tarifa=f["tarifa"],
                periodo=f["periodo"],
                fuente_archivo=f["fuente_archivo"],
                adquirida_kw=Decimal(f["adquirida_kw"]) if f["adquirida_kw"] is not None else None,
                tg_fi_por_bloque=_tg(f),
            )
            for f in FACTURAS_VERIFICADAS_INICIALES
        }
        self._parametros = {
            (f["clave"], f["distribuidora"], f["tarifa"]): Decimal(f["valor"])
            for f in PARAMETROS_REGULATORIOS_INICIALES
        }

    def obtener_tarifa_capacidad(self, distribuidora: str, periodo: str) -> TarifaCapacidad | None:
        return self._tarifas.get((distribuidora, periodo))

    def obtener_factura_verificada(self, planta_id: str, periodo: str) -> FacturaVerificada | None:
        return self._facturas.get((planta_id, periodo))

    def factor_recargo_exceso(self, distribuidora: str, tarifa: str) -> Decimal:
        return self._parametro("factor_recargo_exceso", distribuidora, tarifa)

    def limite_tg_fi_regimen_1992(self, distribuidora: str, tarifa: str) -> Decimal:
        return self._parametro("limite_tg_fi_regimen_1992", distribuidora, tarifa)

    def _parametro(self, clave: str, distribuidora: str, tarifa: str) -> Decimal:
        valor = self._parametros.get((clave, distribuidora, tarifa))
        if valor is None:
            raise LookupError(f"Parámetro regulatorio '{clave}' no cargado para {distribuidora} {tarifa}.")
        return valor
