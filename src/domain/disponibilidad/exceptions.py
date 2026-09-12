"""src/domain/disponibilidad/exceptions.py."""
class DominioDisponibilidadException(Exception):
    """Excepción base del dominio de disponibilidad de máquina."""

    def __init__(self, mensaje: str):
        super().__init__(mensaje)
        self.mensaje = mensaje


class MaquinaNoEncontradaError(DominioDisponibilidadException):
    """Lanzada cuando se intenta operar con una máquina que no existe."""


class EventoDisponibilidadNoEncontradoError(DominioDisponibilidadException):
    """Lanzada cuando se intenta operar con un evento de disponibilidad que no existe."""


class DispositivoYaAsociadoAMaquinaError(DominioDisponibilidadException):
    """Lanzada al asociar un dispositivo que ya tiene una máquina asociada (relación 1:1)."""


class RangoParadaProgramadaInvalidoError(DominioDisponibilidadException):
    """Lanzada cuando el fin de una parada programada es anterior o igual a su inicio."""


class DispositivoDeOrganizacionDistintaError(DominioDisponibilidadException):
    """Lanzada al intentar asociar a una Maquina/ParadaProgramada un dispositivo de otra organización."""
