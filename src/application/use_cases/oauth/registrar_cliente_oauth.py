"""src/application/use_cases/oauth/registrar_cliente_oauth.py — Registro dinámico de clientes OAuth (RFC 7591).

El cliente de Claude (`claude-ai`) solo se asigna si TODAS las redirect_uris pedidas están, tal cual, en la lista
cerrada de Claude. Cualquier otro pedido recibe un `dyn-<uuid>` propio y un nombre que no se pueda confundir con
Claude. El registro nunca ensancha las redirect_uris de un cliente que ya existe (datamaq#131).
"""

import uuid
from collections.abc import Sequence

from src.domain.oauth.entities import OAuthClient
from src.domain.oauth.ports import OAuthRepositoryPort
from src.domain.oauth.services import (
    CLIENT_ID_CLAUDE,
    URIS_REDIRECT_CLAUDE_POR_DEFECTO,
    es_cliente_oficial_de_claude,
    nombre_visible_de_cliente,
)


class RegistrarClienteOAuthUseCase:
    def __init__(
        self,
        oauth_repo: OAuthRepositoryPort,
        claude_redirect_uris: Sequence[str] = URIS_REDIRECT_CLAUDE_POR_DEFECTO,
    ) -> None:
        self.oauth_repo = oauth_repo
        self.claude_redirect_uris = tuple(claude_redirect_uris)

    def ejecutar(self, client_name: str | None, redirect_uris: Sequence[str]) -> OAuthClient:
        oficial = es_cliente_oficial_de_claude(redirect_uris, self.claude_redirect_uris)
        nombre = nombre_visible_de_cliente(client_name, oficial)
        if oficial:
            return self._cliente_de_claude(nombre)
        client_id = f"dyn-{uuid.uuid4().hex[:12]}"
        return self.oauth_repo.registrar_o_actualizar_cliente(client_id, nombre, list(redirect_uris))

    def _cliente_de_claude(self, nombre: str) -> OAuthClient:
        """El cliente fijo de Claude. Si ya existe se devuelve sin modificarlo; sus URIs efectivas son la lista cerrada."""
        existente = self.oauth_repo.obtener_cliente(CLIENT_ID_CLAUDE)
        if existente is None:
            existente = self.oauth_repo.registrar_o_actualizar_cliente(
                CLIENT_ID_CLAUDE, nombre, list(self.claude_redirect_uris)
            )
        return OAuthClient(
            client_id=existente.client_id,
            client_name=existente.client_name,
            redirect_uris=self.claude_redirect_uris,
            created_at=existente.created_at,
        )
