import re
from typing import Any, NoReturn

import structlog
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.adapters.presenters.error_presenter import ErrorPresenter

PATRONES_SONDA_SOSPECHOSA: tuple[re.Pattern[str], ...] = (
    # Directorios de sistema operativo y credenciales sensibles
    re.compile(r"/(?:proc|sys|etc|dev|root|home)/", re.IGNORECASE),
    re.compile(r"/(?:\.env|\.git|\.ssh|\.aws|\.kube|\.docker)", re.IGNORECASE),
    re.compile(r"/(?:\.git-credentials|\.ssh/|id_rsa|id_dsa|id_ed25519)", re.IGNORECASE),
    # Infraestructura y contenedores
    re.compile(r"/(?:dockerfile|docker-compose|compose\.ya?ml)", re.IGNORECASE),
    # Extensiones de archivos de entorno, secretos y configuraciones de infra
    re.compile(
        r"\.(?:env|git|yaml|yml|toml|tfstate|sql|bak|old|swp|save|ini|conf|log|sh|pem|key|rsa|crt)$",
        re.IGNORECASE,
    ),
    # Tecnologías y stacks ajenos al backend (PHP, ASP, JSP, CGI)
    re.compile(r"\.(?:php|asp|aspx|jsp|cgi)(?:/|$|\?)", re.IGNORECASE),
    # Paneles de control y CMS comunes (WordPress, phpMyAdmin, Adminer)
    re.compile(r"/(?:wp-admin|wp-content|wp-includes|phpmyadmin|pma|adminer|xmlrpc\.php)", re.IGNORECASE),
    # Exploits específicos, bots y canarios observados en el incidente
    re.compile(r"(?:node-load-method|customMCP|langflow|debug-trigger)", re.IGNORECASE),
    # Archivos de credenciales o paquetes sensibles
    re.compile(r"/(?:service_account|credentials|package|composer|tsconfig)\.json$", re.IGNORECASE),
    # Secuencias de path traversal o caracteres de control
    re.compile(r"(?:\.\.|%2e%2e|%00|\x00)", re.IGNORECASE),
)


def es_sonda_sospechosa(path: str) -> bool:
    """Determina si una ruta inexistente corresponde a un escaneo automatizado o sonda externa."""
    if not path:
        return False
    path_normalizado = path.strip().lower()
    return any(patron.search(path_normalizado) for patron in PATRONES_SONDA_SOSPECHOSA)



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
    """Loguea rutas inexistentes distinguiendo entre 404 operacional y sonda externa."""
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    if exc.status_code == 404 and exc.detail == "Not Found":
        logger = structlog.get_logger("http_errors")
        path = request.url.path
        es_sonda = es_sonda_sospechosa(path)
        evento = "sonda_sospechosa" if es_sonda else "ruta_no_encontrada"

        client_ip = None
        if request.client:
            client_ip = request.client.host
        x_forwarded_for = request.headers.get("x-forwarded-for")
        if x_forwarded_for:
            client_ip = x_forwarded_for.split(",")[0].strip()

        extra: dict[str, Any] = {
            "metodo": request.method,
            "path": path,
            "request_id": _request_id(),
        }
        if client_ip:
            extra["ip"] = client_ip

        logger.warning(evento, **extra)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)

