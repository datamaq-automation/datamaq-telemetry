"""src/infrastructure/fastapi/error_handler.py — Helper central para mapear excepciones a errores HTTP con logging correlacionado."""

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

    orig = getattr(exc, "orig", None)
    if orig is not None:
        contexto["db_error"] = str(orig)
    statement = getattr(exc, "statement", None)
    if statement is not None:
        contexto["db_statement"] = str(statement)

    if code >= 500:
        logger.error("error_interno", exc_info=True, **contexto)
    else:
        logger.warning("error_negocio", codigo=code, **contexto)
    headers: dict[str, str] | None = None
    retry_after = getattr(exc, "retry_after_seg", None)
    if code == 429 and isinstance(retry_after, int):
        headers = {"Retry-After": str(retry_after)}
    if code >= 500 and request_id:
        headers = headers or {}
        headers["X-Request-ID"] = str(request_id)
    raise HTTPException(status_code=code, detail=err["mensaje"], headers=headers) from exc


def manejar_404(request: Request, exc: Exception) -> JSONResponse:
    """Loguea rutas inexistentes (404 con detail 'Not Found') y reemite la respuesta estándar."""
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    if exc.status_code == 404 and exc.detail == "Not Found":
        logger = structlog.get_logger("http_errors")
        # Un 404 operacional es error del cliente, no degradación del servidor.
        logger.info(
            "ruta_no_encontrada",
            metodo=request.method,
            path=request.url.path,
            request_id=_request_id(),
        )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)
