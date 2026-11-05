"""src/infrastructure/sqlalchemy/repositories/parametros_regulatorios_repository.py.

Adaptador SQLAlchemy de `RepositorioParametrosRegulatoriosPort` (datamaq#111, fase 1). Lee las tablas de
`models_parametros_regulatorios.py`. Si falta un parámetro regulatorio, falla con LookupError: no inventa un valor.
"""

from decimal import Decimal

from sqlalchemy.orm import Session

from src.domain.telemetria.parametros_regulatorios import RepositorioParametrosRegulatoriosPort
from src.domain.telemetria.penalizacion_periodo import FacturaVerificada
from src.domain.telemetria.tarifas_distribuidora import TarifaCapacidad
from src.infrastructure.sqlalchemy.models_parametros_regulatorios import (
    FacturaVerificadaModel,
    ParametroRegulatorioModel,
    TarifaCapacidadModel,
)


class RepositorioParametrosRegulatoriosSqlAlchemy(RepositorioParametrosRegulatoriosPort):
    def __init__(self, db: Session) -> None:
        self.db = db

    def obtener_tarifa_capacidad(self, distribuidora: str, periodo: str) -> TarifaCapacidad | None:
        fila = (
            self.db.query(TarifaCapacidadModel)
            .filter(TarifaCapacidadModel.distribuidora == distribuidora, TarifaCapacidadModel.periodo == periodo)
            .order_by(TarifaCapacidadModel.vigencia_desde.desc(), TarifaCapacidadModel.id.desc())
            .first()
        )
        if fila is None:
            return None
        return TarifaCapacidad(
            distribuidora=fila.distribuidora,
            tarifa=fila.tarifa,
            periodo=fila.periodo,
            fuente_archivo=fila.fuente_archivo,
            vigencia_desde=fila.vigencia_desde.isoformat(),
            importe_capacidad_convenida_ars=Decimal(fila.importe_capacidad_convenida_ars),
            csc_kw=Decimal(fila.csc_kw),
        )

    def obtener_factura_verificada(self, planta_id: str, periodo: str) -> FacturaVerificada | None:
        fila = (
            self.db.query(FacturaVerificadaModel)
            .filter(FacturaVerificadaModel.planta_id == planta_id, FacturaVerificadaModel.periodo == periodo)
            .order_by(FacturaVerificadaModel.id.desc())
            .first()
        )
        if fila is None:
            return None
        bloques = (fila.tg_fi_bloque_punta, fila.tg_fi_bloque_valle, fila.tg_fi_bloque_resto)
        tg = tuple(Decimal(b) for b in bloques if b is not None) or None
        return FacturaVerificada(
            planta_id=fila.planta_id,
            distribuidora=fila.distribuidora,
            tarifa=fila.tarifa,
            periodo=fila.periodo,
            fuente_archivo=fila.fuente_archivo,
            adquirida_kw=Decimal(fila.adquirida_kw) if fila.adquirida_kw is not None else None,
            tg_fi_por_bloque=tg,
        )

    def factor_recargo_exceso(self, distribuidora: str, tarifa: str) -> Decimal:
        return self._valor("factor_recargo_exceso", distribuidora, tarifa)

    def limite_tg_fi_regimen_1992(self, distribuidora: str, tarifa: str) -> Decimal:
        return self._valor("limite_tg_fi_regimen_1992", distribuidora, tarifa)

    def _valor(self, clave: str, distribuidora: str, tarifa: str) -> Decimal:
        fila = (
            self.db.query(ParametroRegulatorioModel)
            .filter(
                ParametroRegulatorioModel.clave == clave,
                ParametroRegulatorioModel.distribuidora == distribuidora,
                ParametroRegulatorioModel.tarifa == tarifa,
            )
            .order_by(ParametroRegulatorioModel.id.desc())
            .first()
        )
        if fila is None:
            raise LookupError(f"Parámetro regulatorio '{clave}' no cargado para {distribuidora} {tarifa}.")
        return Decimal(fila.valor)
