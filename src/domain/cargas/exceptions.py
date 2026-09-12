"""src/domain/cargas/exceptions.py."""
class DominioCargasException(Exception):
    """Excepción base del dominio de desagregación de cargas."""

    def __init__(self, mensaje: str):
        super().__init__(mensaje)
        self.mensaje = mensaje


class CargaNoEncontradaError(DominioCargasException):
    """Lanzada cuando se intenta operar con una carga que no existe."""


class CargaDuplicadaError(DominioCargasException):
    """Lanzada al registrar dos cargas con el mismo nombre bajo el mismo dispositivo."""


class FirmaCargaInvalidaError(DominioCargasException):
    """Lanzada cuando una firma declarada manualmente no describe una carga física posible."""


class CampanaNoEncontradaError(DominioCargasException):
    """Lanzada cuando se intenta operar con una campaña de caracterización que no existe."""


class CampanaEnCursoError(DominioCargasException):
    """Lanzada al abrir una campaña sobre un medidor que ya tiene una en curso.

    Dos campañas simultáneas sobre el mismo medidor medirían la misma señal agregada y
    ninguna de las dos podría atribuirse su parte.
    """


class CampanaYaCerradaError(DominioCargasException):
    """Lanzada al finalizar o descartar una campaña que ya no está en curso."""


class DuracionCampanaInvalidaError(DominioCargasException):
    """Lanzada cuando la duración pedida no alcanza para medir nada o es desmedida."""


class IntervaloActividadNoEncontradoError(DominioCargasException):
    """Lanzada cuando se intenta corregir un intervalo de actividad que no existe."""
