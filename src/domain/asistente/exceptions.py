"""src/domain/asistente/exceptions.py."""


class DominioAsistenteException(Exception):
    """Excepción base del dominio del asistente conversacional."""

    def __init__(self, mensaje: str) -> None:
        self.mensaje = mensaje
        super().__init__(mensaje)


class IntencionNoReconocidaError(DominioAsistenteException):
    """El clasificador no pudo determinar la intención de la consulta con confianza suficiente."""
