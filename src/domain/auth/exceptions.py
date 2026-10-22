"""src/domain/auth/exceptions.py."""


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
        super().__init__(mensaje, usuario=usuario)
        self.retry_after_seg = retry_after_seg


class Codigo2FAInvalidoError(DominioAuthException):
    """Lanzada cuando el código TOTP o código de respaldo no es válido."""


class TokenMFAPendienteInvalidoError(DominioAuthException):
    """Lanzada cuando el token efímero de MFA es inválido o ha expirado."""


class Setup2FAInvalidoError(DominioAuthException):
    """Lanzada cuando no se puede configurar o activar 2FA."""


class TokenRecuperacionInvalidoError(DominioAuthException):
    """Lanzada cuando el token de recuperación de contraseña es inválido, expiró o ya fue usado."""


class ContrasenaDebilError(DominioAuthException):
    """Lanzada cuando la nueva contraseña no cumple con los requisitos mínimos de seguridad."""


class Operacion2FANoDisponibleParaInvitadoError(DominioAuthException):
    """Lanzada cuando un usuario con rol invitado intenta enrolar o gestionar 2FA."""


class UsuarioNoEncontradoError(DominioAuthException):
    """Lanzada cuando se administra un usuario que no existe."""


class CodigoCambioInvalidoError(DominioAuthException):
    """Código inexistente, expirado, ya usado o bloqueado por intentos (siempre 400, sin distinguir)."""


class NoSePudoEnviarCodigoError(DominioAuthException):
    """El email con el código no pudo enviarse; el usuario debe reintentar."""
