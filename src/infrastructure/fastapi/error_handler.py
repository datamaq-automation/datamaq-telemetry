"""Helper central para mapear excepciones a errores HTTP con logging correlacionado."""

from typing import Any, NoReturn

import structlog
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.adapters.presenters.error_presenter import ErrorPresenter


def _request_id() -> Any:
    return structlog.contextvars.get_contextvars().get("request_id")


def _usuario_del_error(exc: Exception) -> Any:
    return getattr(exc, "usuario", None)


def manejar_error_http(exc: Exception) -> NoReturn:
    """Mapea una excepción vía ErrorPresenter, loguea el evento y eleva HTTPException."""
    code, err = ErrorPresenter.presentar_excepcion(exc)
    request_id = _request_id()
    logger = structlog.get_logger("http_errors")
    usuario = _usuario_del_error(exc)
    contexto: dict[str, Any] = {"tipo": type(exc).__name__, "request_id": request_id}
    if usuario is not None:
        contexto["usuario"] = usuario
    if code >= 500:
        logger.error("error_interno", exc_info=True, **contexto)
    else:
        logger.warning("error_negocio", codigo=code, **contexto)
    raise HTTPException(status_code=code, detail=err["mensaje"]) from exc


def manejar_404(request: Request, exc: Exception) -> JSONResponse:
    """Loguea rutas inexistentes (404 con detail 'Not Found') y reemite la respuesta estándar."""
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    if exc.status_code == 404 and exc.detail == "Not Found":
        logger = structlog.get_logger("http_errors")
        logger.warning(
            "ruta_no_encontrada",
            metodo=request.method,
            path=request.url.path,
            request_id=_request_id(),
        )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)
