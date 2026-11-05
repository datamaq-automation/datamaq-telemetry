"""src/domain/telemetria/value_objects.py."""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

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

    def __post_init__(self) -> None:
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

    def __post_init__(self) -> None:
        for nombre, val in (
            ("x_porcentaje", self.x_porcentaje),
            ("y_porcentaje", self.y_porcentaje),
        ):
            if val < 0.0 or val > 100.0:
                raise CoordenadaInvalidaError(f"{nombre} fuera de rango (0-100%): {val}")


@dataclass(frozen=True)
class MacAddress:
    valor: str

    def __post_init__(self) -> None:
        limpio = self.valor.replace(":", "").replace("-", "").upper()
        if not re.fullmatch(r"^[0-9A-F]{12}$", limpio):
            raise MacAddressInvalidaError(f"MAC address inválida: {self.valor}")
        object.__setattr__(self, "valor", limpio)

    @classmethod
    def desde_texto(cls, texto: str) -> "MacAddress":
        """Factory method semántico: normaliza mayúsculas, espacios y separadores comunes."""
        limpio = texto.strip().replace(":", "").replace("-", "").replace(".", "").upper()
        return cls(valor=limpio)

    def formateada(self) -> str:
        return ":".join(self.valor[i : i + 2] for i in range(0, 12, 2))


@dataclass(frozen=True)
class Tension:
    voltios: float

    def __post_init__(self) -> None:
        if self.voltios < 0.0 or self.voltios > 1000.0:
            raise TensionInvalidaError(f"Tensión fuera de rango (0-1000V): {self.voltios}")

    @classmethod
    def desde_kv(cls, kilovoltios: float) -> "Tension":
        """Factory method: construye a partir de kilovoltios (kV -> V)."""
        return cls(voltios=round(kilovoltios * 1000.0, 3))


@dataclass(frozen=True)
class Corriente:
    amperios: float


@dataclass(frozen=True)
class PotenciaActiva:
    vatios: float

    @classmethod
    def desde_kw(cls, kilovatios: float) -> "PotenciaActiva":
        """Factory method: construye a partir de kilovatios (kW -> W)."""
        return cls(vatios=round(kilovatios * 1000.0, 3))


@dataclass(frozen=True)
class PotenciaReactiva:
    var: float

    @classmethod
    def desde_kvar(cls, kilovar: float) -> "PotenciaReactiva":
        """Factory method: construye a partir de kilovar (kvar -> var)."""
        return cls(var=round(kilovar * 1000.0, 3))


@dataclass(frozen=True)
class PotenciaAparente:
    va: float

    @classmethod
    def desde_kva(cls, kilova: float) -> "PotenciaAparente":
        """Factory method: construye a partir de kilovoltamperios (kVA -> VA)."""
        return cls(va=round(kilova * 1000.0, 3))


@dataclass(frozen=True)
class FactorPotencia:
    valor: float

    def __post_init__(self) -> None:
        if self.valor < -1.0 or self.valor > 1.0:
            raise FactorPotenciaInvalidoError(f"Factor de potencia fuera de [-1.0, 1.0]: {self.valor}")

    @classmethod
    def desde_potencias(cls, activa_w: float, aparente_va: float) -> "FactorPotencia":
        """Factory method: deriva el factor de potencia P/S acotado al rango [-1.0, 1.0]."""
        if aparente_va <= 0.0:
            return cls(valor=1.0)
        fp = round(activa_w / aparente_va, 4)
        return cls(valor=min(1.0, max(-1.0, fp)))


@dataclass(frozen=True)
class EnergiaActiva:
    kwh: float

    @classmethod
    def desde_mwh(cls, megavatios_hora: float) -> "EnergiaActiva":
        """Factory method: construye a partir de megavatios-hora (MWh -> kWh)."""
        return cls(kwh=round(megavatios_hora * 1000.0, 3))


@dataclass(frozen=True)
class EnergiaReactiva:
    kvarh: float

    @classmethod
    def desde_mvarh(cls, megavar_hora: float) -> "EnergiaReactiva":
        """Factory method: construye a partir de megavar-hora (Mvarh -> kvarh)."""
        return cls(kvarh=round(megavar_hora * 1000.0, 3))


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

    asociacion_tension_corriente: tuple[str, ...] = ("R", "S", "T")
    polaridad_ti: bool = False

    def __post_init__(self) -> None:
        if not (1 <= len(self.asociacion_tension_corriente) <= 3):
            raise ValueError(f"Orden de fases debe tener 1-3 elementos: {self.asociacion_tension_corriente}")
        for fase in self.asociacion_tension_corriente:
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
        if indice >= len(self.asociacion_tension_corriente):
            raise ValueError(f"Índice {indice} fuera de rango para {len(self.asociacion_tension_corriente)} fases")

        p, q, s, fp = medicion.p, medicion.q, medicion.s, medicion.fp

        if self.polaridad_ti and q is not None:
            q = -q

        return MedicionFase(p=p, q=q, s=s, fp=fp)

    def posicion_legible(self) -> str:
        """Representación legible: asociación + (INV) si aplica."""
        inv_str = " (INV)" if self.polaridad_ti else ""
        return f"{','.join(self.asociacion_tension_corriente)}{inv_str}"


@dataclass(frozen=True)
class CandidatoTI:
    """Candidato de configuración de TI (orden de fases e inversión) con score.

    Resultado del ranking de diagnóstico: representa una hipótesis sobre cómo
    deben estar ordenadas las fases y si la polaridad está invertida.
    """

    asociacion_tension_corriente: tuple[str, ...]
    polaridad_ti: bool
    score: float
    justificacion: str

    def posicion(self) -> str:
        """Representación legible: asociación + (INV) si aplica."""
        inv_str = " (INV)" if self.polaridad_ti else ""
        return f"{','.join(self.asociacion_tension_corriente)}{inv_str}"

    def __post_init__(self) -> None:
        if self.score < 0.0 or self.score > 1.0:
            raise ValueError(f"Score fuera de rango [0.0, 1.0]: {self.score}")
        if not (1 <= len(self.asociacion_tension_corriente) <= 3):
            raise ValueError(f"Orden de fases debe tener 1-3 elementos: {self.asociacion_tension_corriente}")
        for fase in self.asociacion_tension_corriente:
            if fase not in ("R", "S", "T"):
                raise ValueError(f"Fase inválida (debe ser R, S o T): {fase}")
