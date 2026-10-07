"""src/domain/telemetria/value_objects.py."""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Literal

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
    factor_potencia_estimado_simetrico: float | None = None
    accion_correctiva_sugerida: str | None = None


@dataclass(frozen=True)
class CoordenadasNodoUnifilar:
    """Coordenadas relativas y geometría para renderizado vectorial 2D del unifilar."""

    x: float
    y: float
    ancho: float | None = None
    orientacion: str | None = None  # "horizontal" | "vertical"


@dataclass(frozen=True)
class InterruptorCabecera:
    """Órgano de maniobra y protección en la cabecera del nodo (tablero o alimentador)."""

    tag: str
    tipo: str | None = None  # ej. "ACB", "MCCB", "SECCIONADOR"
    in_a: float | None = None
    icu_ka: float | None = None
    estado: str = "cerrado"  # "cerrado", "abierto", "desconocido"


@dataclass(frozen=True)
class MetadatosPlaca:
    """Parámetros electrotécnicos nominales de placa (IEC / IEEE / ANSI)."""

    potencia_nominal_kva: float | None = None
    relacion_tension_kv: str | None = None
    vsc_porcentaje: float | None = None
    grupo_conexion: str | None = None
    corriente_nominal_a: float | None = None
    icw_ka: float | None = None
    frecuencia_hz: float | None = 50.0
    calibre_in_a: float | None = None
    cable_seccion: str | None = None
    longitud_estimada_m: float | None = None
    tension_nominal_v: float | None = None
    categoria_tarifaria: str | None = None
    trafo_asociado_kva: float | None = None
    corriente_barra_a: float | None = None
    proteccion_in_a: float | None = None
    datos_adicionales: dict[str, Any] | None = None


@dataclass(frozen=True)
class MedicionFase:
    """Medición de potencias y factor de una fase (P, Q, S, FP).

    Value object inmutable para un punto en el tiempo de una fase específica.
    """

    p: float | None = None
    q: float | None = None
    s: float | None = None
    fp: float | None = None


@dataclass(frozen=True)
class RotacionFasorial:
    """Transformación fasorial: reorden de fases + inversión de polaridad.

    Value object inmutable que encapsula una configuración de rotación fasorial
    (orden de fases + inversión de Q). Usado para:
    - Diagnóstico de TI (orden de fases e inversión)
    - Simulación de rotaciones en análisis metrológico
    """

    orden_fases: tuple[str, ...] = ("R", "S", "T")
    invertida: bool = False

    def __post_init__(self) -> None:
        if not (1 <= len(self.orden_fases) <= 3):
            raise ValueError(f"Orden de fases debe tener 1-3 elementos: {self.orden_fases}")
        for fase in self.orden_fases:
            if fase not in ("R", "S", "T"):
                raise ValueError(f"Fase inválida (debe ser R, S o T): {fase}")

    def aplicar_a_fase(self, medicion: "MedicionFase", indice: int) -> "MedicionFase":
        """Aplica rotación a una medición de fase por su índice en el reorden.

        Args:
            medicion: Medición original (P, Q, S, FP)
            indice: Posición en el reorden (0=R, 1=S, 2=T)

        Returns:
            MedicionFase con Q invertida si aplica, resto sin cambios
        """
        if indice >= len(self.orden_fases):
            raise ValueError(f"Índice {indice} fuera de rango para {len(self.orden_fases)} fases")

        p, q, s, fp = medicion.p, medicion.q, medicion.s, medicion.fp

        if self.invertida and q is not None:
            q = -q

        return MedicionFase(p=p, q=q, s=s, fp=fp)

    def posicion_legible(self) -> str:
        """Representación legible: orden + (INV) si aplica."""
        inv_str = " (INV)" if self.invertida else ""
        return f"{','.join(self.orden_fases)}{inv_str}"


@dataclass(frozen=True)
class CandidatoTI:
    """Candidato de configuración de TI (orden de fases e inversión) con score.

    Resultado del ranking de diagnóstico: representa una hipótesis sobre cómo
    deben estar ordenadas las fases y si la polaridad está invertida.
    """

    orden_fases: tuple[str, ...]
    invertido: bool
    score: float
    justificacion: str

    def posicion(self) -> str:
        """Representación legible: orden + (INV) si aplica."""
        inv_str = " (INV)" if self.invertido else ""
        return f"{','.join(self.orden_fases)}{inv_str}"

    def __post_init__(self) -> None:
        if self.score < 0.0 or self.score > 1.0:
            raise ValueError(f"Score fuera de rango [0.0, 1.0]: {self.score}")
        if not (1 <= len(self.orden_fases) <= 3):
            raise ValueError(f"Orden de fases debe tener 1-3 elementos: {self.orden_fases}")
        for fase in self.orden_fases:
            if fase not in ("R", "S", "T"):
                raise ValueError(f"Fase inválida (debe ser R, S o T): {fase}")


class GranularidadTelemetria(str, Enum):
    """Granularidades permitidas en la telemetría histórica."""

    CINCO_MINUTOS = "5m"
    QUINCE_MINUTOS = "15m"
    TREINTA_MINUTOS = "30m"
    UNA_HORA = "1h"
    UN_DIA = "1d"


PeriodoTelemetria = Literal["24h", "7d", "30d"]


class ConfigGranularidadPeriodo:
    """Configuración de granularidades permitidas y default por período."""

    def __init__(
        self,
        opciones: list[GranularidadTelemetria],
        default: GranularidadTelemetria,
    ) -> None:
        self.opciones = opciones
        self.default = default


GRANULARIDADES_POR_PERIODO: dict[PeriodoTelemetria, ConfigGranularidadPeriodo] = {
    "24h": ConfigGranularidadPeriodo(
        opciones=[
            GranularidadTelemetria.CINCO_MINUTOS,
            GranularidadTelemetria.QUINCE_MINUTOS,
            GranularidadTelemetria.TREINTA_MINUTOS,
        ],
        default=GranularidadTelemetria.CINCO_MINUTOS,
    ),
    "7d": ConfigGranularidadPeriodo(
        opciones=[
            GranularidadTelemetria.QUINCE_MINUTOS,
            GranularidadTelemetria.TREINTA_MINUTOS,
            GranularidadTelemetria.UNA_HORA,
        ],
        default=GranularidadTelemetria.TREINTA_MINUTOS,
    ),
    "30d": ConfigGranularidadPeriodo(
        opciones=[
            GranularidadTelemetria.UNA_HORA,
            GranularidadTelemetria.UN_DIA,
        ],
        default=GranularidadTelemetria.UNA_HORA,
    ),
}


def obtener_default_granularidad(periodo: PeriodoTelemetria) -> GranularidadTelemetria:
    """Retorna la granularidad por defecto para un período dado."""
    config = GRANULARIDADES_POR_PERIODO.get(periodo)
    if not config:
        raise ValueError(f"Período no válido: {periodo}")
    return config.default


def validar_granularidad(
    granularidad: str | GranularidadTelemetria, periodo: PeriodoTelemetria
) -> GranularidadTelemetria:
    """Valida que la granularidad sea válida para el período dado.

    Raises:
        ValueError: Si granularidad no es válida para el período.
    """
    # Convertir a enum si es string
    if isinstance(granularidad, str):
        try:
            granularidad_enum = GranularidadTelemetria(granularidad)
        except ValueError:
            valores_validos = ", ".join(g.value for g in GranularidadTelemetria)
            raise ValueError(f"Granularidad '{granularidad}' no reconocida. Válidas: {valores_validos}") from None
    else:
        granularidad_enum = granularidad

    # Verificar que sea válida para el período
    config = GRANULARIDADES_POR_PERIODO.get(periodo)
    if not config:
        raise ValueError(f"Período no válido: {periodo}")

    if granularidad_enum not in config.opciones:
        valores_validos = ", ".join(g.value for g in config.opciones)
        raise ValueError(
            f"Granularidad '{granularidad_enum.value}' no válida para período '{periodo}'. Válidas: {valores_validos}"
        )

    return granularidad_enum
