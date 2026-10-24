"""src/application/use_cases/oauth/autorizar_consentimiento.py — Genera código temporal de autorización con PKCE."""

from datetime import datetime, timedelta, timezone

import structlog

from src.application.dtos.oauth_dtos import OAuthAuthorizeRequestDTO, OAuthAuthorizeResponseDTO
from src.domain.oauth.entities import OAuthCode
from src.domain.oauth.exceptions import InvalidClientError, InvalidRequestError
from src.domain.oauth.ports import OAuthRepositoryPort
from src.domain.oauth.services import generar_token_aleatorio, hash_token, resolver_scopes

_log = structlog.get_logger(__name__)


class AutorizarConsentimientoUseCase:
    """Caso de uso para registrar el consentimiento del usuario y emitir un authorization code PKCE."""

    def __init__(self, oauth_repo: OAuthRepositoryPort) -> None:
        self.oauth_repo = oauth_repo

    def ejecutar(
        self,
        dto: OAuthAuthorizeRequestDTO,
        usuario_id: str,
        organizacion_id: str | None = None,
    ) -> OAuthAuthorizeResponseDTO:
        cliente = self.oauth_repo.obtener_cliente(dto.client_id)
        if cliente is None:
            raise InvalidClientError(f"Cliente '{dto.client_id}' no registrado")

        # Validar que la redirect_uri esté autorizada para este cliente
        # Aceptar coincidencia exacta o coincidencia de prefijo seguro
        uri_valida = any(
            dto.redirect_uri == autorizada or dto.redirect_uri.startswith(autorizada.rstrip("*"))
            for autorizada in cliente.redirect_uris
        )
        if not uri_valida:
            raise InvalidRequestError("redirect_uri no autorizada para el cliente solicitado")

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

        sep = "&" if "?" in dto.redirect_uri else "?"
        query_params = f"code={code}"
        if dto.state:
            query_params += f"&state={dto.state}"
        url_retorno = f"{dto.redirect_uri}{sep}{query_params}"

        return OAuthAuthorizeResponseDTO(
            code=code,
            state=dto.state,
            redirect_uri=url_retorno,
        )
