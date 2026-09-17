"""src/domain/telemetria/value_objects.py."""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from src.domain.telemetria.exceptions import (
    CoordenadaInvalidaError,
    FactorPotenciaInvalidoError,
    MacAddressInvalidaError,
    TensionInvalidaError,
)


class EstadoDispositivo(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    WARNING = "WARNING"


class SeveridadAlerta(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class ReglaAlertaConectividad:
    timeout_segundos: int = 300
    max_reconexiones_ventana: int = 3
    ventana_reconexiones_minutos: int = 30
    rssi_umbral_dbm: int = -78
    calidad_umbral_pct: int = 40


class VisibilidadPlan(str, Enum):
    PUBLICO = "PUBLICO"
    PRIVADO = "PRIVADO"


class ModoFreeTier(str, Enum):
    PRIVADO_BASICO = "PRIVADO_BASICO"


class TipoNodoUnifilar(str, Enum):
    ACOMETIDA = "acometida"
    TRANSFORMADOR = "transformador"
    TGBT = "tgbt"
    SECCIONAL = "seccional"
    CARGA = "carga"


class GranularidadEnergia(str, Enum):
    DIA = "day"
    MES = "month"


@dataclass(frozen=True)
class CoordenadasZona:
    x_porcentaje: float
    y_porcentaje: float
    ancho_porcentaje: float
    alto_porcentaje: float

    def __post_init__(self):
        for nombre, val in (
            ("x_porcentaje", self.x_porcentaje),
            ("y_porcentaje", self.y_porcentaje),
            ("ancho_porcentaje", self.ancho_porcentaje),
            ("alto_porcentaje", self.alto_porcentaje),
        ):
            if val < 0.0 or val > 100.0:
                raise CoordenadaInvalidaError(f"{nombre} fuera de rango (0-100%): {val}")


@dataclass(frozen=True)
class PosicionLayout:
    x_porcentaje: float
    y_porcentaje: float

    def __post_init__(self):
        for nombre, val in (
            ("x_porcentaje", self.x_porcentaje),
            ("y_porcentaje", self.y_porcentaje),
        ):
            if val < 0.0 or val > 100.0:
                raise CoordenadaInvalidaError(f"{nombre} fuera de rango (0-100%): {val}")


@dataclass(frozen=True)
class MacAddress:
    valor: str

    def __post_init__(self):
        limpio = self.valor.replace(":", "").replace("-", "").upper()
        if not re.fullmatch(r"^[0-9A-F]{12}$", limpio):
            raise MacAddressInvalidaError(f"MAC address inválida: {self.valor}")
        object.__setattr__(self, "valor", limpio)

    def formateada(self) -> str:
        return ":".join(self.valor[i : i + 2] for i in range(0, 12, 2))


@dataclass(frozen=True)
class Tension:
    voltios: float

    def __post_init__(self):
        if self.voltios < 0.0 or self.voltios > 1000.0:
            raise TensionInvalidaError(f"Tensión fuera de rango (0-1000V): {self.voltios}")


@dataclass(frozen=True)
class Corriente:
    amperios: float


@dataclass(frozen=True)
class PotenciaActiva:
    vatios: float


@dataclass(frozen=True)
class PotenciaReactiva:
    var: float


@dataclass(frozen=True)
class PotenciaAparente:
    va: float


@dataclass(frozen=True)
class FactorPotencia:
    valor: float

    def __post_init__(self):
        if self.valor < -1.0 or self.valor > 1.0:
            raise FactorPotenciaInvalidoError(f"Factor de potencia fuera de [-1.0, 1.0]: {self.valor}")


@dataclass(frozen=True)
class EnergiaActiva:
    kwh: float


@dataclass(frozen=True)
class EnergiaReactiva:
    kvarh: float


class EstadoFactorPotencia(str, Enum):
    OPTIMO = "OPTIMO"
    ADVERTENCIA = "ADVERTENCIA"
    PENALIZADO = "PENALIZADO"
    SIN_DATOS = "SIN_DATOS"


class EstadoTension(str, Enum):
    NORMAL = "NORMAL"
    SUBTENSION = "SUBTENSION"
    SOBRETENSION = "SOBRETENSION"
    SIN_DATOS = "SIN_DATOS"


@dataclass(frozen=True)
class AnaliticaCalidadEnergia:
    requiere_compensacion: bool
    potencia_reactiva_a_compensar_kvar: float | None = None
    banco_sugerido_kvar: float | None = None
    penalizacion_estimada_ars: float | None = None
    desbalance_tension_porcentaje: float | None = None
    desbalance_corriente_porcentaje: float | None = None
    estado_fp: EstadoFactorPotencia = EstadoFactorPotencia.SIN_DATOS
    estado_tension: EstadoTension = EstadoTension.SIN_DATOS
    recargo_porcentaje: float | None = 0.0
    motivo_abstencion: str | None = None
    ventana_evaluacion_min: int | None = 15
    vigente_desde: datetime | None = None
    factor_potencia_integrado: float | None = None


@dataclass(frozen=True)
class LecturaPotenciaTemporal:
    """Par (momento, potencia) para análisis de la serie de potencia.

    Deliberadamente liviano: el análisis de regímenes recorre potencialmente millones de
    filas, y construir una `LecturaInstantanea` completa (fases, THD, tensiones) por cada
    una sería caro e innecesario.

    `potencia_reactiva_var` y `factor_potencia` son opcionales y solo los completa quien
    los necesita: la desagregación de cargas los usa para separar una carga resistiva
    (FP≈1, Q≈0) de una con motor (FP 0.5-0.8, Q alta), que es el eje de firmas de Hart.
    La segmentación de regímenes los ignora, y por eso llegan con default en vez de
    obligar a todos los productores de la serie a leer dos columnas más.
    """

    momento: datetime
    potencia_w: float
    potencia_reactiva_var: float | None = None
    factor_potencia: float | None = None


class EstadoMetrologicoLectura(str, Enum):
    CONFIABLE = "CONFIABLE"
    DEGRADADO = "DEGRADADO"
    NO_CONFIABLE = "NO_CONFIABLE"


@dataclass(frozen=True)
class DiagnosticoInstalacion:
    """Diagnóstico de calidad metrológica e integridad física de la instalación."""

    estado_metrologico: EstadoMetrologicoLectura = EstadoMetrologicoLectura.CONFIABLE
    fases_validas: tuple[str, ...] = ("R", "S", "T")
    fases_comprometidas: tuple[str, ...] = ()
    anomalias_detectadas: tuple[str, ...] = ()
    potencia_estimada_simetrica_w: float | None = None
    accion_correctiva_sugerida: str | None = None
