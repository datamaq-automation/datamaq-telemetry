class DominioAuthException(Exception):
    """Excepción base del dominio de autenticación."""

    def __init__(self, mensaje: str):
        super().__init__(mensaje)
        self.mensaje = mensaje


class NombreUsuarioInvalidoError(DominioAuthException):
    """Lanzada cuando el nombre de usuario queda vacío tras normalizar."""


class CredencialesInvalidasError(DominioAuthException):
    """Lanzada cuando el usuario no existe o la contraseña es incorrecta."""


class UsuarioInactivoError(DominioAuthException):
    """Lanzada cuando la cuenta del usuario está deshabilitada."""
