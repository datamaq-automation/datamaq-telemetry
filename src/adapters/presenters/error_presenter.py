from typing import Any

from src.domain.telemetria.exceptions import (
    DispositivoNoEncontradoError,
    DominioTelemetriaException,
    FactorPotenciaInvalidoError,
    MacAddressInvalidaError,
    TensionInvalidaError,
)


class ErrorPresenter:
    """Presenter agnóstico de transporte para mapear excepciones a estructuras de error y códigos HTTP."""

    @staticmethod
    def presentar_excepcion(exc: Exception) -> tuple[int, dict[str, Any]]:
        if isinstance(exc, DispositivoNoEncontradoError):
            return 404, {"error": "NotFound", "mensaje": exc.mensaje}
        elif isinstance(exc, (MacAddressInvalidaError, TensionInvalidaError, FactorPotenciaInvalidoError)):
            return 400, {"error": "ValidationError", "mensaje": exc.mensaje}
        elif isinstance(exc, DominioTelemetriaException):
            return 422, {"error": "DomainError", "mensaje": exc.mensaje}
        return 500, {"error": "InternalServerError", "mensaje": str(exc)}
