"""add 2fa totp fields to users

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-09-06 20:55:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5c6d7e8f9a0"
down_revision: str | Sequence[str] | None = "a4b5c6d7e8f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_cols = {c["name"] for c in inspector.get_columns("users")}

    if "totp_secret" not in existing_cols:
        op.add_column("users", sa.Column("totp_secret", sa.String(255), nullable=True))
    if "totp_enabled" not in existing_cols:
        op.add_column("users", sa.Column("totp_enabled", sa.Boolean(), server_default=sa.false(), nullable=False))
    if "totp_backup_codes" not in existing_cols:
        op.add_column("users", sa.Column("totp_backup_codes", sa.JSON(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_cols = {c["name"] for c in inspector.get_columns("users")}

    if "totp_backup_codes" in existing_cols:
        op.drop_column("users", "totp_backup_codes")
    if "totp_enabled" in existing_cols:
        op.drop_column("users", "totp_enabled")
    if "totp_secret" in existing_cols:
        op.drop_column("users", "totp_secret")
