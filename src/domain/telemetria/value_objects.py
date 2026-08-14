import re
from dataclasses import dataclass
from enum import Enum

from src.domain.telemetria.exceptions import (
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
