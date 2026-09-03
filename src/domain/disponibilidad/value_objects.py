from enum import Enum


class EstadoMaquina(str, Enum):
    MARCHA = "MARCHA"
    PARADA = "PARADA"


class TipoParada(str, Enum):
    PROGRAMADA = "PROGRAMADA"
    NO_PROGRAMADA = "NO_PROGRAMADA"
    SIN_CLASIFICAR = "SIN_CLASIFICAR"


class OrigenClasificacion(str, Enum):
    REGLA = "REGLA"
    CORRECCION_HUMANA = "CORRECCION_HUMANA"
