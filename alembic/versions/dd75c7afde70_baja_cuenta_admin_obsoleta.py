"""baja_cuenta_admin_obsoleta

Revision ID: dd75c7afde70
Revises: f1a2b3c4d5e6
Create Date: 2026-11-05 15:05:12.569948

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dd75c7afde70"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema: elimina cuenta semilla obsoleta admin@datamaq.com.ar."""
    op.execute("DELETE FROM users WHERE username = 'admin@datamaq.com.ar'")


def downgrade() -> None:
    """Downgrade schema."""
    pass
