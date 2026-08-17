"""Helper central para mapear excepciones a errores HTTP con logging correlacionado."""

from typing import NoReturn

import structlog
from fastapi import HTTPException

from src.adapters.presenters.error_presenter import ErrorPresenter


def manejar_error_http(exc: Exception) -> NoReturn:
    """Mapea una excepción vía ErrorPresenter, loguea el evento y eleva HTTPException."""
    code, err = ErrorPresenter.presentar_excepcion(exc)
    request_id = structlog.contextvars.get_contextvars().get("request_id")
    logger = structlog.get_logger("http_errors")
    if code >= 500:
        logger.error("error_interno", exc_info=True, tipo=type(exc).__name__, request_id=request_id)
    else:
        logger.warning("error_negocio", tipo=type(exc).__name__, codigo=code, request_id=request_id)
    raise HTTPException(status_code=code, detail=err["mensaje"]) from exc
