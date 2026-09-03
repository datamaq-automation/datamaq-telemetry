from typing import Any

from src.domain.auth.exceptions import (
    CredencialesInvalidasError,
    DemasiadosIntentosError,
    NombreUsuarioInvalidoError,
    UsuarioInactivoError,
)
from src.domain.disponibilidad.exceptions import (
    DominioDisponibilidadException,
    EventoDisponibilidadNoEncontradoError,
    MaquinaNoEncontradaError,
)
from src.domain.telemetria.exceptions import (
    AlertaNoEncontradaError,
    DispositivoNoEncontradoError,
    DominioTelemetriaException,
    FactorPotenciaInvalidoError,
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
            ),
        ):
            return 404, {"error": "NotFound", "mensaje": exc.mensaje}
        elif isinstance(exc, (MacAddressInvalidaError, TensionInvalidaError, FactorPotenciaInvalidoError)):
            return 400, {"error": "ValidationError", "mensaje": exc.mensaje}
        elif isinstance(exc, (DominioTelemetriaException, DominioDisponibilidadException)):
            return 422, {"error": "DomainError", "mensaje": exc.mensaje}
        elif isinstance(exc, NombreUsuarioInvalidoError):
            return 422, {"error": "ValidationError", "mensaje": exc.mensaje}
        elif isinstance(exc, CredencialesInvalidasError):
            return 401, {"error": "Unauthorized", "mensaje": "credenciales_invalidas"}
        elif isinstance(exc, UsuarioInactivoError):
            return 403, {"error": "Forbidden", "mensaje": "usuario_inactivo"}
        elif isinstance(exc, DemasiadosIntentosError):
            return 429, {"error": "TooManyRequests", "mensaje": exc.mensaje}

        return 500, {"error": "InternalServerError", "mensaje": "Ocurrió un error interno en el servidor"}
