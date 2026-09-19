"""src/domain/produccion/entities.py — Entidades para gestión de producción y EnPI híbrido."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ModoMedicion(str, Enum):
    """Modo de medición energética para la máquina."""

    DEDICADA_SECCIONAL = "DEDICADA_SECCIONAL"
    AGREGADA_TGBT = "AGREGADA_TGBT"


@dataclass(frozen=True)
class ConfiguracionMedicionMaquina:
    """Configuración topológica y de sensórica de una máquina para el cálculo de EnPI."""

    maquina_id: str
    nombre: str
    potencia_nominal_kw: float
    nodo_alimentacion: str
    dispositivo_medidor_id: str | None = None
    factor_escala_longitud: float = 1.0
    factor_escala_cortes: float = 1.0

    @property
    def es_medicion_dedicada(self) -> bool:
        """Determina si la máquina cuenta con medidor eléctrico exclusivo en TS/CCM."""
        return self.dispositivo_medidor_id is not None

    @property
    def modo_medicion(self) -> ModoMedicion:
        """Retorna el modo de medición correspondiente a la topología de la máquina."""
        return ModoMedicion.DEDICADA_SECCIONAL if self.es_medicion_dedicada else ModoMedicion.AGREGADA_TGBT


@dataclass(frozen=True)
class ResultadoSecHibrido:
    """Resultado del cálculo de Consumo Específico (SEC) según topología de medición."""

    maquina_id: str
    modo_medicion: ModoMedicion
    periodo_inicio: datetime
    periodo_fin: datetime
    energia_total_kwh: float
    unidades_procesadas: float
    sec_kwh_por_unidad: float | None
    energia_productiva_kwh: float
    energia_no_productiva_kwh: float
    ratio_desperdicio_pct: float
    detalle_estimacion: str | None = None
