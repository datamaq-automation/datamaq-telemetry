"""src/application/use_cases/oauth/autorizar_consentimiento.py — Genera código temporal de autorización con PKCE."""

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

import structlog

from src.application.dtos.oauth_dtos import OAuthAuthorizeRequestDTO, OAuthAuthorizeResponseDTO
from src.domain.oauth.entities import OAuthClient, OAuthCode
from src.domain.oauth.exceptions import InvalidClientError, InvalidRequestError
from src.domain.oauth.ports import OAuthRepositoryPort
from src.domain.oauth.services import (
    CLIENT_ID_CLAUDE,
    URIS_REDIRECT_CLAUDE_POR_DEFECTO,
    construir_url_retorno,
    generar_token_aleatorio,
    hash_token,
    redirect_uri_autorizada,
    resolver_scopes,
)

_log = structlog.get_logger(__name__)


class AutorizarConsentimientoUseCase:
    """Caso de uso para registrar el consentimiento del usuario y emitir un authorization code PKCE."""

    def __init__(
        self,
        oauth_repo: OAuthRepositoryPort,
        claude_redirect_uris: Sequence[str] = URIS_REDIRECT_CLAUDE_POR_DEFECTO,
    ) -> None:
        self.oauth_repo = oauth_repo
        self.claude_redirect_uris = tuple(claude_redirect_uris)

    def _cliente_con_redirect_uri_valida(self, client_id: str, redirect_uri: str) -> OAuthClient:
        """El cliente, si existe y la redirect_uri coincide EXACTAMENTE con una de las suyas (datamaq#131).

        Para el cliente de Claude manda la lista cerrada configurada, no lo que haya guardado en su fila.
        """
        cliente = self.oauth_repo.obtener_cliente(client_id)
        if cliente is None:
            raise InvalidClientError(f"Cliente '{client_id}' no registrado")
        autorizadas = self.claude_redirect_uris if client_id == CLIENT_ID_CLAUDE else cliente.redirect_uris
        if not redirect_uri_autorizada(redirect_uri, autorizadas):
            raise InvalidRequestError("redirect_uri no autorizada para el cliente solicitado")
        return cliente

    def cancelar(self, client_id: str, redirect_uri: str, state: str | None) -> str:
        """URL a la que vuelve el usuario que canceló. Solo hacia una redirect_uri autorizada del cliente."""
        self._cliente_con_redirect_uri_valida(client_id, redirect_uri)
        parametros = {"error": "access_denied", "error_description": "El usuario cancelo la autorizacion"}
        if state:
            parametros["state"] = state
        return construir_url_retorno(redirect_uri, parametros)

    def ejecutar(
        self,
        dto: OAuthAuthorizeRequestDTO,
        usuario_id: str,
        organizacion_id: str | None = None,
    ) -> OAuthAuthorizeResponseDTO:
        self._cliente_con_redirect_uri_valida(dto.client_id, dto.redirect_uri)

        if dto.code_challenge_method != "S256":
            raise InvalidRequestError("code_challenge_method debe ser 'S256'")

        # Scopes desconocidos: se descartan (no se rechaza, porque el servidor todavía no aplica scopes) y se
        # registran para saber qué piden realmente los conectores.
        scope, descartados = resolver_scopes(dto.scope)
        if descartados:
            _log.warning(
                "oauth_scopes_desconocidos_descartados",
                client_id=dto.client_id,
                descartados=list(descartados),
                otorgados=scope,
            )

        ahora = datetime.now(timezone.utc)
        expira_en = ahora + timedelta(minutes=5)
        code = generar_token_aleatorio(32)
        code_hash = hash_token(code)

        oauth_code = OAuthCode(
            code_hash=code_hash,
            client_id=dto.client_id,
            user_id=usuario_id,
            organization_id=organizacion_id,
            redirect_uri=dto.redirect_uri,
            code_challenge=dto.code_challenge,
            code_challenge_method=dto.code_challenge_method,
            scope=scope,
            expires_at=expira_en,
            used=False,
            created_at=ahora,
        )
        self.oauth_repo.guardar_codigo(oauth_code)

        parametros = {"code": code}
        if dto.state:
            parametros["state"] = dto.state
        url_retorno = construir_url_retorno(dto.redirect_uri, parametros)

        return OAuthAuthorizeResponseDTO(
            code=code,
            state=dto.state,
            redirect_uri=url_retorno,
        )
