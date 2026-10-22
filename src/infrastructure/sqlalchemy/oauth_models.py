"""src/infrastructure/sqlalchemy/oauth_models.py — Modelos ORM para OAuth 2.0 PKCE."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.sqlalchemy.models import Base, ahora_utc
from src.infrastructure.sqlalchemy.types import UtcDateTime

if TYPE_CHECKING:
    from src.infrastructure.sqlalchemy.models import UserModel


class OAuthClientModel(Base):
    """Clientes registrados para el servidor de autorización OAuth 2.0 (ej. Claude.ai)."""

    __tablename__ = "oauth_clients"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    client_name: Mapped[str] = mapped_column(String(128), nullable=False)
    redirect_uris: Mapped[str] = mapped_column(Text, nullable=False)  # URLs separadas por coma
    is_trusted: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)


class OAuthCodeModel(Base):
    """Códigos de autorización temporales emitidos con PKCE (TTL 5 minutos)."""

    __tablename__ = "oauth_codes"
    __table_args__ = (
        Index("idx_oauth_codes_client_user", "client_id", "user_id"),
        Index("idx_oauth_codes_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    redirect_uri: Mapped[str] = mapped_column(String(512), nullable=False)
    code_challenge: Mapped[str] = mapped_column(String(128), nullable=False)
    code_challenge_method: Mapped[str] = mapped_column(
        String(16), default="S256", server_default="S256", nullable=False
    )
    scope: Mapped[str] = mapped_column(
        String(256), default="read:telemetria read:analitica read:alertas", nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)

    usuario: Mapped["UserModel"] = relationship()


class OAuthRefreshTokenModel(Base):
    """Refresh tokens de actualización para conectores autorizados (TTL 30 días con rotación)."""

    __tablename__ = "oauth_refresh_tokens"
    __table_args__ = (
        Index("idx_oauth_refresh_tokens_client_user", "client_id", "user_id"),
        Index("idx_oauth_refresh_tokens_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    scope: Mapped[str] = mapped_column(
        String(256), default="read:telemetria read:analitica read:alertas", nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)

    usuario: Mapped["UserModel"] = relationship()
