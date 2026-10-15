"""src/application/use_cases/oauth/canjear_token_oauth.py — Canje de autorización y refresh tokens según RFC 6749 y RFC 7636."""

from datetime import datetime, timedelta, timezone

from src.application.dtos.oauth_dtos import OAuthTokenRequestDTO, OAuthTokenResponseDTO
from src.domain.auth.ports import GeneradorTokenPort, RepositorioUsuariosPort
from src.domain.oauth.entities import OAuthRefreshToken
from src.domain.oauth.exceptions import (
    InvalidGrantError,
    InvalidRequestError,
    UnsupportedGrantTypeError,
)
from src.domain.oauth.ports import OAuthRepositoryPort
from src.domain.oauth.services import (
    generar_token_aleatorio,
    hash_token,
    verificar_code_verifier,
)


class CanjearTokenOAuthUseCase:
    """Caso de uso para canjear un código de autorización (PKCE) o rotar un refresh token."""

    def __init__(
        self,
        oauth_repo: OAuthRepositoryPort,
        token_service: GeneradorTokenPort,
        usuario_repo: RepositorioUsuariosPort | None = None,
    ) -> None:
        self.oauth_repo = oauth_repo
        self.token_service = token_service
        self.usuario_repo = usuario_repo

    def ejecutar(self, dto: OAuthTokenRequestDTO) -> OAuthTokenResponseDTO:
        ahora = datetime.now(timezone.utc)

        if dto.grant_type == "authorization_code":
            return self._canjear_authorization_code(dto, ahora)
        elif dto.grant_type == "refresh_token":
            return self._canjear_refresh_token(dto, ahora)
        else:
            raise UnsupportedGrantTypeError(f"Tipo de grant '{dto.grant_type}' no soportado")

    def _canjear_authorization_code(self, dto: OAuthTokenRequestDTO, ahora: datetime) -> OAuthTokenResponseDTO:
        if not dto.code or not dto.code_verifier or not dto.redirect_uri:
            raise InvalidRequestError("Faltan parámetros requeridos: code, code_verifier o redirect_uri")

        code_hash = hash_token(dto.code)
        oauth_code = self.oauth_repo.obtener_codigo(code_hash)

        if oauth_code is None:
            raise InvalidGrantError("Código de autorización inexistente o inválido")

        if oauth_code.used:
            raise InvalidGrantError("El código de autorización ya fue utilizado")

        if oauth_code.expires_at < ahora:
            raise InvalidGrantError("El código de autorización ha expirado")

        if dto.client_id and dto.client_id != oauth_code.client_id:
            raise InvalidGrantError("client_id no coincide con el código de autorización emitido")

        if dto.redirect_uri != oauth_code.redirect_uri:
            raise InvalidGrantError("redirect_uri no coincide con la autorizada inicialmente")

        if not verificar_code_verifier(dto.code_verifier, oauth_code.code_challenge, oauth_code.code_challenge_method):
            raise InvalidGrantError("code_verifier no coincide con el code_challenge")

        # Consumo atómico para prevenir condiciones de carrera y ataques de repetición
        consumido = self.oauth_repo.consumir_codigo(code_hash)
        if not consumido:
            raise InvalidGrantError("El código de autorización ya fue utilizado")

        # Obtener información del usuario para claims
        usuario = self.usuario_repo.obtener_por_id(oauth_code.user_id) if self.usuario_repo else None
        username = usuario.usuario if usuario else oauth_code.user_id
        rol = usuario.rol if usuario else "operador"

        # Emisión de Access Token JWT (TTL 24 horas = 86400s)
        expira_access = ahora + timedelta(days=1)
        access_token = self.token_service.generar(
            usuario_id=oauth_code.user_id,
            usuario=username,
            expira_en=expira_access,
            rol=rol,
            organizacion_id=oauth_code.organization_id,
            scope=oauth_code.scope,
            client_id=oauth_code.client_id,
        )

        # Emisión de Refresh Token criptográfico con rotación (TTL 30 días)
        refresh_token = generar_token_aleatorio(32)
        refresh_hash = hash_token(refresh_token)
        expira_refresh = ahora + timedelta(days=30)
        token_entidad = OAuthRefreshToken(
            token_hash=refresh_hash,
            client_id=oauth_code.client_id,
            user_id=oauth_code.user_id,
            organization_id=oauth_code.organization_id,
            scope=oauth_code.scope,
            expires_at=expira_refresh,
            revoked_at=None,
            created_at=ahora,
        )
        self.oauth_repo.guardar_refresh_token(token_entidad)

        return OAuthTokenResponseDTO(
            access_token=access_token,
            token_type="bearer",
            expires_in=86400,
            refresh_token=refresh_token,
            scope=oauth_code.scope,
        )

    def _canjear_refresh_token(self, dto: OAuthTokenRequestDTO, ahora: datetime) -> OAuthTokenResponseDTO:
        if not dto.refresh_token:
            raise InvalidRequestError("Falta parámetro requerido: refresh_token")

        token_hash = hash_token(dto.refresh_token)
        token_entidad = self.oauth_repo.obtener_refresh_token(token_hash)

        if token_entidad is None or token_entidad.revoked_at is not None:
            raise InvalidGrantError("Refresh token inexistente o revocado")

        if token_entidad.expires_at < ahora:
            raise InvalidGrantError("Refresh token expirado")

        if dto.client_id and dto.client_id != token_entidad.client_id:
            raise InvalidGrantError("client_id no coincide con el refresh token emitido")

        # Rotación estricta de refresh token. Se guarda el nuevo ANTES de revocar el viejo: get_usuario_actual
        # exige un refresh activo para los access tokens OAuth, y un hueco entre ambas escrituras daría 401.
        nuevo_refresh = generar_token_aleatorio(32)
        nuevo_hash = hash_token(nuevo_refresh)
        expira_nuevo = ahora + timedelta(days=30)
        nuevo_entidad = OAuthRefreshToken(
            token_hash=nuevo_hash,
            client_id=token_entidad.client_id,
            user_id=token_entidad.user_id,
            organization_id=token_entidad.organization_id,
            scope=token_entidad.scope,
            expires_at=expira_nuevo,
            revoked_at=None,
            created_at=ahora,
        )
        self.oauth_repo.guardar_refresh_token(nuevo_entidad)
        self.oauth_repo.revocar_refresh_token(token_hash, ahora)

        usuario = self.usuario_repo.obtener_por_id(token_entidad.user_id) if self.usuario_repo else None
        username = usuario.usuario if usuario else token_entidad.user_id
        rol = usuario.rol if usuario else "operador"

        expira_access = ahora + timedelta(days=1)
        access_token = self.token_service.generar(
            usuario_id=token_entidad.user_id,
            usuario=username,
            expira_en=expira_access,
            rol=rol,
            organizacion_id=token_entidad.organization_id,
            scope=token_entidad.scope,
            client_id=token_entidad.client_id,
        )

        return OAuthTokenResponseDTO(
            access_token=access_token,
            token_type="bearer",
            expires_in=86400,
            refresh_token=nuevo_refresh,
            scope=token_entidad.scope,
        )
