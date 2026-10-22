"""src/application/use_cases/oauth/revocar_token_oauth.py — Revocación de tokens según RFC 7009."""

from datetime import datetime, timezone

from src.application.dtos.oauth_dtos import OAuthRevokeRequestDTO
from src.domain.oauth.ports import OAuthRepositoryPort
from src.domain.oauth.services import hash_token


class RevocarTokenOAuthUseCase:
    """Caso de uso para revocar un token OAuth 2.0 (RFC 7009)."""

    def __init__(self, oauth_repo: OAuthRepositoryPort) -> None:
        self.oauth_repo = oauth_repo

    def ejecutar(self, dto: OAuthRevokeRequestDTO) -> None:
        ahora = datetime.now(timezone.utc)
        token_hash = hash_token(dto.token)

        # Intenta revocar como refresh_token
        self.oauth_repo.revocar_refresh_token(token_hash, ahora)
        # Según RFC 7009 §2.2, si el token no existe o ya está revocado, el servidor igualmente responde éxito.
