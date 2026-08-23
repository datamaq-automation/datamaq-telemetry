class DominioTelemetriaException(Exception):
    """Excepción base del dominio de telemetría."""

    def __init__(self, mensaje: str):
        super().__init__(mensaje)
        self.mensaje = mensaje


class MacAddressInvalidaError(DominioTelemetriaException):
    """Lanzada cuando la MAC address no cumple con el formato estándar."""


class DispositivoNoEncontradoError(DominioTelemetriaException):
    """Lanzada cuando se intenta operar con un dispositivo que no existe."""


class FormatoMedicionInvalidoError(DominioTelemetriaException):
    """Lanzada cuando los datos de medición son inconsistentes o nulos."""


class FactorPotenciaInvalidoError(DominioTelemetriaException):
    """Lanzada cuando el factor de potencia está fuera de [-1.0, 1.0]."""


class TensionInvalidaError(DominioTelemetriaException):
    """Lanzada cuando un valor de tensión es negativo o fuera de rango físico."""


class LimiteDispositivosExcedidoError(DominioTelemetriaException):
    """Lanzada cuando una organización intenta asociar más dispositivos que los permitidos por su plan."""


class AlertaNoEncontradaError(DominioTelemetriaException):
    """Lanzada cuando se intenta operar con una alerta que no existe."""


class CoordenadaInvalidaError(DominioTelemetriaException):
    """Lanzada cuando una coordenada o dimensión porcentual está fuera del rango [0.0, 100.0]."""


class PlantaNoEncontradaError(DominioTelemetriaException):
    """Lanzada cuando se intenta operar con una planta que no existe."""
