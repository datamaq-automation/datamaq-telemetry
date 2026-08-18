class DominioAuthException(Exception):
    """Excepción base del dominio de autenticación."""

    def __init__(self, mensaje: str, usuario: str | None = None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.usuario = usuario


class NombreUsuarioInvalidoError(DominioAuthException):
    """Lanzada cuando el nombre de usuario queda vacío tras normalizar."""


class CredencialesInvalidasError(DominioAuthException):
    """Lanzada cuando el usuario no existe o la contraseña es incorrecta."""


class UsuarioInactivoError(DominioAuthException):
    """Lanzada cuando la cuenta del usuario está deshabilitada."""


class DemasiadosIntentosError(DominioAuthException):
    """Lanzada cuando se excede el límite de intentos de inicio de sesión."""

    def __init__(self, mensaje: str, usuario: str | None = None, retry_after_seg: int | None = None):
        super().__init__(mensaje, usuario)
        self.retry_after_seg = retry_after_seg
