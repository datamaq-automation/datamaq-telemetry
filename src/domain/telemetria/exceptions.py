"""src/domain/telemetria/exceptions.py."""


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


class CortePurgaFuturoError(DominioTelemetriaException):
    """Lanzada cuando el corte de purga (corte_hasta) es posterior al instante actual."""


class GranularidadEnergiaInvalidaError(DominioTelemetriaException):
    """Lanzada cuando la granularidad de energía solicitada no es day ni month."""


class ZonaHorariaInvalidaError(DominioTelemetriaException):
    """Lanzada cuando el identificador IANA de zona horaria no existe o es inválido."""


class GrupoDispositivosNoEncontradoError(DominioTelemetriaException):
    """Lanzada cuando se intenta operar con un grupo de dispositivos que no existe."""


class DispositivoDePlantaDistintaError(DominioTelemetriaException):
    """Lanzada al intentar agregar a un grupo un dispositivo de otra planta."""


class LimiteGruposExcedidoError(DominioTelemetriaException):
    """Lanzada cuando una planta intenta crear más grupos de dispositivos que el tope permitido."""
