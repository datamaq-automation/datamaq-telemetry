"""Módulo de configuración y resolución de cookies de autenticación (ISO 27001 / Clean Architecture).

Gestiona la fijación y eliminación de cookies HttpOnly, adaptando dinámicamente
la directiva SameSite (SameSite=None; Secure para orígenes cross-site Cybersyn,
y la política nativa estricta para el ecosistema Datamaq).
"""

from typing import Literal
from urllib.parse import urlparse

from fastapi import Request, Response

from src.infrastructure.settings.config import Settings

ORIGENES_CORS_CYBERSYN: tuple[str, ...] = (
    "https://cybersyn.com.ar",
    "https://www.cybersyn.com.ar",
)

CYBERSYN_HOSTS: frozenset[str] = frozenset({"cybersyn.com.ar", "www.cybersyn.com.ar"})

DEVICE_TRUST_COOKIE = "datamaq_device_trust"
DEVICE_TRUST_MAX_AGE = 60 * 60 * 24 * 30  # 30 días


def es_origen_cybersyn(request: Request | None) -> bool:
    """Verifica si la petición proviene de un origen o referer del dominio Cybersyn."""
    if request is None or not hasattr(request, "headers"):
        return False
    headers = request.headers
    origin = headers.get("origin") if hasattr(headers, "get") else None
    if origin:
        parsed = urlparse(origin)
        if parsed.hostname in CYBERSYN_HOSTS:
            return True
    referer = headers.get("referer") if hasattr(headers, "get") else None
    if referer:
        parsed = urlparse(referer)
        if parsed.hostname in CYBERSYN_HOSTS:
            return True
    return False


def resolver_politica_cookie(
    request: Request | None,
    settings: Settings,
) -> tuple[Literal["lax", "strict", "none"], bool]:
    """Resuelve SameSite y Secure según el origen de la petición.

    Para orígenes cross-site de Cybersyn, retorna ('none', True).
    Para el ecosistema nativo Datamaq, preserva la configuración de Settings.
    """
    if request is not None and es_origen_cybersyn(request):
        return ("none", True)
    return (settings.AUTH_COOKIE_SAMESITE, settings.auth_cookie_secure)


def fijar_cookie_auth(
    response: Response,
    settings: Settings,
    token: str,
    request: Request | None = None,
) -> None:
    """Fija la cookie de sesión HttpOnly con política de SameSite adaptativa."""
    samesite, secure = resolver_politica_cookie(request, settings)
    response.set_cookie(
        key=settings.AUTH_COOKIE_NOMBRE,
        value=token,
        max_age=settings.auth_cookie_max_age,
        httponly=settings.AUTH_COOKIE_HTTPONLY,
        samesite=samesite,
        secure=secure,
    )


def fijar_cookie_dispositivo(
    response: Response,
    settings: Settings,
    token: str,
    request: Request | None = None,
) -> None:
    """Fija la cookie de dispositivo confiable (2FA) con política SameSite adaptativa."""
    samesite, secure = resolver_politica_cookie(request, settings)
    response.set_cookie(
        key=DEVICE_TRUST_COOKIE,
        value=token,
        max_age=DEVICE_TRUST_MAX_AGE,
        httponly=True,
        samesite=samesite,
        secure=secure,
        path="/api/v1/auth",
    )


def eliminar_cookie_auth(
    response: Response,
    settings: Settings,
    request: Request | None = None,
) -> None:
    """Elimina la cookie de sesión asegurando directivas coherentes en cross-site."""
    samesite, secure = resolver_politica_cookie(request, settings)
    response.delete_cookie(
        key=settings.AUTH_COOKIE_NOMBRE,
        httponly=settings.AUTH_COOKIE_HTTPONLY,
        samesite=samesite,
        secure=secure,
    )


# Alias retrocompatibles
_fijar_cookie = fijar_cookie_auth
_fijar_cookie_dispositivo = fijar_cookie_dispositivo
_eliminar_cookie = eliminar_cookie_auth
