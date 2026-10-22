"""feat_oauth_tablas_autorizacion_pkce

Revision ID: 7603c19a617f
Revises: b7c3d9e1f2a4
Create Date: 2026-10-10 16:11:18.891836

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7603c19a617f"
down_revision: str | Sequence[str] | None = "b7c3d9e1f2a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "oauth_clients",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("client_id", sa.String(128), nullable=False),
        sa.Column("client_name", sa.String(128), nullable=False),
        sa.Column("redirect_uris", sa.Text(), nullable=False),
        sa.Column("is_trusted", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id"),
    )
    op.create_index("ix_oauth_clients_client_id", "oauth_clients", ["client_id"])

    op.create_table(
        "oauth_codes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("client_id", sa.String(128), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=True),
        sa.Column("redirect_uri", sa.String(512), nullable=False),
        sa.Column("code_challenge", sa.String(128), nullable=False),
        sa.Column("code_challenge_method", sa.String(16), server_default="S256", nullable=False),
        sa.Column("scope", sa.String(256), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash"),
    )
    op.create_index("idx_oauth_codes_client_user", "oauth_codes", ["client_id", "user_id"])
    op.create_index("idx_oauth_codes_expires_at", "oauth_codes", ["expires_at"])

    op.create_table(
        "oauth_refresh_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("client_id", sa.String(128), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=True),
        sa.Column("scope", sa.String(256), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("idx_oauth_refresh_tokens_client_user", "oauth_refresh_tokens", ["client_id", "user_id"])
    op.create_index("idx_oauth_refresh_tokens_expires_at", "oauth_refresh_tokens", ["expires_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_oauth_refresh_tokens_expires_at", table_name="oauth_refresh_tokens")
    op.drop_index("idx_oauth_refresh_tokens_client_user", table_name="oauth_refresh_tokens")
    op.drop_table("oauth_refresh_tokens")

    op.drop_index("idx_oauth_codes_expires_at", table_name="oauth_codes")
    op.drop_index("idx_oauth_codes_client_user", table_name="oauth_codes")
    op.drop_table("oauth_codes")

    op.drop_index("ix_oauth_clients_client_id", table_name="oauth_clients")
    op.drop_table("oauth_clients")
