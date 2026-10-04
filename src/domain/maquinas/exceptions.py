"""src/domain/maquinas/exceptions.py."""


class DominioMáquinasException(Exception):
    """Excepción base del dominio de desagregación de máquinas."""

    def __init__(self, mensaje: str):
        super().__init__(mensaje)
        self.mensaje = mensaje


class MáquinaNoEncontradaError(DominioMáquinasException):
    """Lanzada cuando se intenta operar con una máquina que no existe."""


class MáquinaDuplicadaError(DominioMáquinasException):
    """Lanzada al registrar dos máquinas con el mismo nombre bajo el mismo dispositivo."""


class FirmaMáquinaInvalidaError(DominioMáquinasException):
    """Lanzada cuando una firma declarada manualmente no describe una máquina física posible."""


class EnsayoNoEncontradoError(DominioMáquinasException):
    """Lanzada cuando se intenta operar con un ensayo de caracterización que no existe."""


class EnsayoEnCursoError(DominioMáquinasException):
    """Lanzada al abrir un ensayo sobre un medidor que ya tiene uno en curso.

    Dos ensayos simultáneos sobre el mismo medidor medirían la misma señal agregada y
    ninguno de los dos podría atribuirse su parte.
    """


class EnsayoYaCerradoError(DominioMáquinasException):
    """Lanzada al finalizar o descartar un ensayo que ya no está en curso."""


class DuracionEnsayoInvalidaError(DominioMáquinasException):
    """Lanzada cuando la duración pedida no alcanza para medir nada o es desmedida."""


class IntervaloActividadNoEncontradoError(DominioMáquinasException):
    """Lanzada cuando se intenta corregir un intervalo de actividad que no existe."""


class DescubridorNoDisponibleError(DominioMáquinasException):
    """Lanzada cuando el servicio externo de descubrimiento de máquinas no responde."""
