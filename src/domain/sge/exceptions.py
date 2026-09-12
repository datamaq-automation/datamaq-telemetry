"""src/domain/sge/exceptions.py."""
class DominioSgeException(Exception):
    """Excepción base del dominio SGE ISO 50001."""

    def __init__(self, mensaje: str):
        self.mensaje = mensaje
        super().__init__(mensaje)


class ArticuloSgeNoEncontradoError(DominioSgeException):
    """El artículo de documentación SGE solicitado no existe."""


class RolNoAutorizadoParaPrevisualizacionError(DominioSgeException):
    """El rol del usuario no tiene privilegios para previsualizar documentación de otros roles."""
