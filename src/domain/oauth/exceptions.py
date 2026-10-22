"""src/domain/oauth/exceptions.py — Excepciones de dominio para el Servidor OAuth 2.0 (RFC 6749)."""


class OAuthError(Exception):
    """Excepción base para errores OAuth 2.0 con código de error RFC 6749."""

    def __init__(self, error: str, description: str, status_code: int = 400) -> None:
        super().__init__(description)
        self.error = error
        self.description = description
        self.status_code = status_code


class InvalidRequestError(OAuthError):
    def __init__(self, description: str) -> None:
        super().__init__("invalid_request", description, status_code=400)


class InvalidClientError(OAuthError):
    def __init__(self, description: str = "Cliente OAuth no registrado o no autorizado") -> None:
        super().__init__("invalid_client", description, status_code=401)


class InvalidGrantError(OAuthError):
    def __init__(self, description: str = "El código o token provisto es inválido, expiró o ya fue utilizado") -> None:
        super().__init__("invalid_grant", description, status_code=400)


class UnauthorizedClientError(OAuthError):
    def __init__(self, description: str = "Cliente no autorizado para esta operación") -> None:
        super().__init__("unauthorized_client", description, status_code=403)


class UnsupportedGrantTypeError(OAuthError):
    def __init__(self, description: str = "Tipo de grant no soportado") -> None:
        super().__init__("unsupported_grant_type", description, status_code=400)


class InvalidScopeError(OAuthError):
    def __init__(self, description: str = "El scope solicitado no es válido") -> None:
        super().__init__("invalid_scope", description, status_code=400)
