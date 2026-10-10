"""src/application/use_cases/oauth/gestionar_integraciones_usuario.py — Consulta y revocación de integraciones del perfil de usuario."""

from datetime import datetime, timezone
from typing import Any

from src.domain.oauth.ports import OAuthRepositoryPort


class GestionarIntegracionesUsuarioUseCase:
    """Caso de uso para visualizar y revocar conexiones autorizadas de un usuario (ISO 27001)."""

    def __init__(self, oauth_repo: OAuthRepositoryPort) -> None:
        self.oauth_repo = oauth_repo

    def listar(self, usuario_id: str) -> list[dict[str, Any]]:
        return self.oauth_repo.listar_integraciones_usuario(usuario_id)

    def revocar_por_cliente(self, usuario_id: str, client_id: str) -> int:
        ahora = datetime.now(timezone.utc)
        return self.oauth_repo.revocar_tokens_usuario_cliente(usuario_id, client_id, ahora)
