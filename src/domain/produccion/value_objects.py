"""src/domain/produccion/value_objects.py — Value Objects para variables de proceso, sensórica inductiva y métricas EnPI."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class TipoVariableProceso(str, Enum):
    LONGITUD_METROS = "LONGITUD_METROS"
    CONTEO_CORTES = "CONTEO_CORTES"
    CICLOS_PRENSA = "CICLOS_PRENSA"
    VELOCIDAD_AVANCE_M_MIN = "VELOCIDAD_AVANCE_M_MIN"
    PIEZAS = "PIEZAS"


@dataclass(frozen=True)
class LecturaVariableProceso:
    momento: datetime
    variable_tipo: TipoVariableProceso
    delta_valor: float
    valor_acumulado: float


@dataclass(frozen=True)
class MetricasConsumoEspecifico:
    periodo_inicio: datetime
    periodo_fin: datetime
    energia_kwh: float
    unidades_procesadas: float
    sec_kwh_por_unidad: float | None
