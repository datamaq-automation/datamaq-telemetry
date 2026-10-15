"""src/infrastructure/sqlalchemy/repositories/oauth_repository.py — Persistencia de clientes, códigos y tokens OAuth 2.0."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from src.domain.oauth.entities import OAuthClient, OAuthCode, OAuthRefreshToken
from src.domain.oauth.ports import OAuthRepositoryPort
from src.infrastructure.sqlalchemy.models import (
    OAuthClientModel,
    OAuthCodeModel,
    OAuthRefreshTokenModel,
)

CLIENTES_PREDETERMINADOS = [
    {
        "client_id": "claude-ai",
        "client_name": "Claude (Anthropic)",
        "redirect_uris": (
            "https://claude.ai/api/mcp/oauth/callback,"
            "https://claude.ai/api/mcp/oauth_callback,"
            "https://claude.com/api/mcp/oauth/callback,"
            "https://claude.com/api/mcp/oauth_callback"
        ),
    },
    {
        "client_id": "datamaq-mcp-client",
        "client_name": "DataMaq MCP Connector",
        "redirect_uris": "http://localhost:8000/callback,http://127.0.0.1:8000/callback,http://localhost:3000/callback",
    },
]


def sembrar_clientes_oauth(db: Session) -> None:
    """Asegura la presencia y actualización de clientes predeterminados como Claude.ai en oauth_clients."""
    for c in CLIENTES_PREDETERMINADOS:
        existente = db.query(OAuthClientModel).filter(OAuthClientModel.client_id == c["client_id"]).first()
        if not existente:
            db.add(
                OAuthClientModel(
                    client_id=c["client_id"],
                    client_name=c["client_name"],
                    redirect_uris=c["redirect_uris"],
                    is_trusted=True,
                )
            )
        else:
            # Sincronizar URIs si se agregaron nuevas en la spec
            uris_actuales = set(u.strip() for u in existente.redirect_uris.split(",") if u.strip())
            uris_deseadas = set(u.strip() for u in c["redirect_uris"].split(",") if u.strip())
            if not uris_deseadas.issubset(uris_actuales):
                todas = sorted(uris_actuales.union(uris_deseadas))
                existente.redirect_uris = ",".join(todas)
    try:
        db.commit()
    except Exception:
        db.rollback()


class MySQLOAuthRepository(OAuthRepositoryPort):
    """Implementación SQLAlchemy del repositorio para OAuth 2.0 y PKCE."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def obtener_cliente(self, client_id: str) -> OAuthClient | None:
        model = self.db.query(OAuthClientModel).filter(OAuthClientModel.client_id == client_id).first()
        if not model:
            # Sembrar dinámicamente si es un cliente predeterminado conocido
            for c in CLIENTES_PREDETERMINADOS:
                if c["client_id"] == client_id:
                    nuevo = OAuthClientModel(
                        client_id=c["client_id"],
                        client_name=c["client_name"],
                        redirect_uris=c["redirect_uris"],
                        is_trusted=True,
                    )
                    self.db.add(nuevo)
                    try:
                        self.db.commit()
                        model = nuevo
                    except Exception:
                        self.db.rollback()
                        model = self.db.query(OAuthClientModel).filter(OAuthClientModel.client_id == client_id).first()
                    break

        if not model:
            return None

        uris_set = set(u.strip() for u in model.redirect_uris.split(",") if u.strip())
        for c in CLIENTES_PREDETERMINADOS:
            if c["client_id"] == client_id:
                uris_set.update(u.strip() for u in c["redirect_uris"].split(",") if u.strip())
        uris = tuple(sorted(uris_set))
        return OAuthClient(
            client_id=model.client_id,
            client_name=model.client_name,
            redirect_uris=uris,
            created_at=model.created_at,
        )

    def guardar_codigo(self, codigo: OAuthCode) -> None:
        model = OAuthCodeModel(
            code_hash=codigo.code_hash,
            client_id=codigo.client_id,
            user_id=codigo.user_id,
            organization_id=codigo.organization_id,
            redirect_uri=codigo.redirect_uri,
            code_challenge=codigo.code_challenge,
            code_challenge_method=codigo.code_challenge_method,
            scope=codigo.scope,
            expires_at=codigo.expires_at,
            used=codigo.used,
            created_at=codigo.created_at,
        )
        self.db.add(model)
        self.db.commit()

    def obtener_codigo(self, code_hash: str) -> OAuthCode | None:
        model = self.db.query(OAuthCodeModel).filter(OAuthCodeModel.code_hash == code_hash).first()
        if not model:
            return None
        return OAuthCode(
            code_hash=model.code_hash,
            client_id=model.client_id,
            user_id=model.user_id,
            organization_id=model.organization_id,
            redirect_uri=model.redirect_uri,
            code_challenge=model.code_challenge,
            code_challenge_method=model.code_challenge_method,
            scope=model.scope,
            expires_at=model.expires_at,
            used=model.used,
            created_at=model.created_at,
        )

    def consumir_codigo(self, code_hash: str) -> bool:
        filas = (
            self.db.query(OAuthCodeModel)
            .filter(OAuthCodeModel.code_hash == code_hash, OAuthCodeModel.used.is_(False))
            .update({"used": True})
        )
        self.db.commit()
        return filas > 0

    def guardar_refresh_token(self, refresh_token: OAuthRefreshToken) -> None:
        model = OAuthRefreshTokenModel(
            token_hash=refresh_token.token_hash,
            client_id=refresh_token.client_id,
            user_id=refresh_token.user_id,
            organization_id=refresh_token.organization_id,
            scope=refresh_token.scope,
            expires_at=refresh_token.expires_at,
            revoked_at=refresh_token.revoked_at,
            created_at=refresh_token.created_at,
        )
        self.db.add(model)
        self.db.commit()

    def obtener_refresh_token(self, token_hash: str) -> OAuthRefreshToken | None:
        model = self.db.query(OAuthRefreshTokenModel).filter(OAuthRefreshTokenModel.token_hash == token_hash).first()
        if not model:
            return None
        return OAuthRefreshToken(
            token_hash=model.token_hash,
            client_id=model.client_id,
            user_id=model.user_id,
            organization_id=model.organization_id,
            scope=model.scope,
            expires_at=model.expires_at,
            revoked_at=model.revoked_at,
            created_at=model.created_at,
        )

    def revocar_refresh_token(self, token_hash: str, ahora: datetime) -> bool:
        filas = (
            self.db.query(OAuthRefreshTokenModel)
            .filter(
                OAuthRefreshTokenModel.token_hash == token_hash,
                OAuthRefreshTokenModel.revoked_at.is_(None),
            )
            .update({"revoked_at": ahora})
        )
        self.db.commit()
        return filas > 0

    def revocar_tokens_usuario_cliente(self, user_id: str, client_id: str, ahora: datetime) -> int:
        filas = (
            self.db.query(OAuthRefreshTokenModel)
            .filter(
                OAuthRefreshTokenModel.user_id == user_id,
                OAuthRefreshTokenModel.client_id == client_id,
                OAuthRefreshTokenModel.revoked_at.is_(None),
            )
            .update({"revoked_at": ahora})
        )
        self.db.commit()
        return filas

    def tiene_integracion_activa(
        self, user_id: str, client_id: str, refresh_creado_hasta: datetime | None = None
    ) -> bool:
        consulta = self.db.query(OAuthRefreshTokenModel.id).filter(
            OAuthRefreshTokenModel.user_id == user_id,
            OAuthRefreshTokenModel.client_id == client_id,
            OAuthRefreshTokenModel.revoked_at.is_(None),
        )
        if refresh_creado_hasta is not None:
            consulta = consulta.filter(OAuthRefreshTokenModel.created_at <= refresh_creado_hasta)
        return consulta.first() is not None

    def listar_integraciones_usuario(self, user_id: str) -> list[dict[str, Any]]:
        ahora = datetime.now(timezone.utc)
        tokens = (
            self.db.query(OAuthRefreshTokenModel)
            .filter(
                OAuthRefreshTokenModel.user_id == user_id,
                OAuthRefreshTokenModel.revoked_at.is_(None),
                OAuthRefreshTokenModel.expires_at > ahora,
            )
            .all()
        )

        integraciones: dict[str, dict[str, Any]] = {}
        for t in tokens:
            if t.client_id not in integraciones:
                cliente = self.obtener_cliente(t.client_id)
                integraciones[t.client_id] = {
                    "client_id": t.client_id,
                    "client_name": cliente.client_name if cliente else t.client_id,
                    "scope": t.scope,
                    "created_at": t.created_at,
                }

        return list(integraciones.values())

    def registrar_o_actualizar_cliente(self, client_id: str, client_name: str, redirect_uris: list[str]) -> OAuthClient:
        model = self.db.query(OAuthClientModel).filter(OAuthClientModel.client_id == client_id).first()
        uris_nuevas = set(u.strip() for u in redirect_uris if u.strip())
        if model:
            uris_existentes = set(u.strip() for u in model.redirect_uris.split(",") if u.strip())
            todas = sorted(uris_existentes.union(uris_nuevas))
            model.redirect_uris = ",".join(todas)
            if client_name and model.client_name != client_name and client_name != "Claude":
                model.client_name = client_name
            self.db.commit()
        else:
            ahora = datetime.now(timezone.utc)
            model = OAuthClientModel(
                client_id=client_id,
                client_name=client_name or "Cliente Dinámico",
                redirect_uris=",".join(sorted(uris_nuevas)),
                is_trusted=True,
                created_at=ahora,
            )
            self.db.add(model)
            self.db.commit()

        return OAuthClient(
            client_id=model.client_id,
            client_name=model.client_name,
            redirect_uris=tuple(u.strip() for u in model.redirect_uris.split(",") if u.strip()),
            created_at=model.created_at,
        )
