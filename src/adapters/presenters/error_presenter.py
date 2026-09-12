"""src/adapters/presenters/error_presenter.py."""

from typing import Any

from src.domain.auth.exceptions import (
    Codigo2FAInvalidoError,
    ContrasenaDebilError,
    CredencialesInvalidasError,
    DemasiadosIntentosError,
    NombreUsuarioInvalidoError,
    Operacion2FANoDisponibleParaInvitadoError,
    Setup2FAInvalidoError,
    TokenMFAPendienteInvalidoError,
    TokenRecuperacionInvalidoError,
    UsuarioInactivoError,
)
from src.domain.cargas.exceptions import (
    CampanaNoEncontradaError,
    CargaNoEncontradaError,
    DominioCargasException,
    FirmaCargaInvalidaError,
    IntervaloActividadNoEncontradoError,
)
from src.domain.disponibilidad.exceptions import (
    DominioDisponibilidadException,
    EventoDisponibilidadNoEncontradoError,
    MaquinaNoEncontradaError,
)
from src.domain.sge.exceptions import (
    ArticuloSgeNoEncontradoError,
    DominioSgeException,
    RolNoAutorizadoParaPrevisualizacionError,
)
from src.domain.telemetria.exceptions import (
    AlertaNoEncontradaError,
    DispositivoNoEncontradoError,
    DominioTelemetriaException,
    FactorPotenciaInvalidoError,
    GrupoDispositivosNoEncontradoError,
    MacAddressInvalidaError,
    PlantaNoEncontradaError,
    TensionInvalidaError,
)


class ErrorPresenter:
    """Presenter agnóstico de transporte para mapear excepciones a estructuras de error y códigos HTTP."""

    @staticmethod
    def presentar_excepcion(exc: Exception) -> tuple[int, dict[str, Any]]:
        if isinstance(
            exc,
            (
                DispositivoNoEncontradoError,
                AlertaNoEncontradaError,
                PlantaNoEncontradaError,
                MaquinaNoEncontradaError,
                EventoDisponibilidadNoEncontradoError,
                CargaNoEncontradaError,
                CampanaNoEncontradaError,
                IntervaloActividadNoEncontradoError,
                GrupoDispositivosNoEncontradoError,
                ArticuloSgeNoEncontradoError,
            ),
        ):
            return 404, {"error": "NotFound", "mensaje": exc.mensaje}
        elif isinstance(
            exc, (MacAddressInvalidaError, TensionInvalidaError, FactorPotenciaInvalidoError, FirmaCargaInvalidaError)
        ):
            return 400, {"error": "ValidationError", "mensaje": exc.mensaje}
        elif isinstance(exc, RolNoAutorizadoParaPrevisualizacionError):
            return 403, {"error": "Forbidden", "mensaje": exc.mensaje}
        elif isinstance(
            exc,
            (
                DominioTelemetriaException,
                DominioDisponibilidadException,
                DominioCargasException,
                DominioSgeException,
            ),
        ):
            return 422, {"error": "DomainError", "mensaje": exc.mensaje}
        elif isinstance(exc, NombreUsuarioInvalidoError):
            return 422, {"error": "ValidationError", "mensaje": exc.mensaje}
        elif isinstance(exc, CredencialesInvalidasError):
            return 401, {"error": "Unauthorized", "mensaje": "credenciales_invalidas"}
        elif isinstance(exc, TokenMFAPendienteInvalidoError):
            return 401, {"error": "Unauthorized", "mensaje": "token_mfa_invalido"}
        elif isinstance(exc, Codigo2FAInvalidoError):
            return 400, {"error": "ValidationError", "mensaje": "codigo_2fa_invalido"}
        elif isinstance(exc, Setup2FAInvalidoError):
            return 400, {"error": "ValidationError", "mensaje": "setup_2fa_invalido"}
        elif isinstance(exc, TokenRecuperacionInvalidoError):
            return 400, {"error": "ValidationError", "mensaje": "token_recuperacion_invalido"}
        elif isinstance(exc, ContrasenaDebilError):
            return 400, {"error": "ValidationError", "mensaje": "contrasena_debil"}
        elif isinstance(exc, UsuarioInactivoError):
            return 403, {"error": "Forbidden", "mensaje": "usuario_inactivo"}
        elif isinstance(exc, Operacion2FANoDisponibleParaInvitadoError):
            return 403, {"error": "Forbidden", "mensaje": "2fa_no_disponible_para_invitado"}
        elif isinstance(exc, DemasiadosIntentosError):
            return 429, {"error": "TooManyRequests", "mensaje": exc.mensaje}

        return 500, {"error": "InternalServerError", "mensaje": "Ocurrió un error interno en el servidor"}
