"""feat(infra): OTP de cambio de contraseña guardado como HMAC y con intentos fallidos

La tabla cambio_contrasena_validaciones está vacía en producción: ningún código escribió en
ella (los endpoints anteriores eran stubs que solo auditaban). Por eso se puede cambiar la
columna `codigo` (texto plano de 4 caracteres) por `codigo_hash` sin migrar datos.

Revision ID: b7c3d9e1f2a4
Revises: 1a35ebb54900
Create Date: 2026-10-08 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7c3d9e1f2a4"
down_revision: str | Sequence[str] | None = "1a35ebb54900"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column("cambio_contrasena_validaciones", "codigo")
    op.add_column(
        "cambio_contrasena_validaciones",
        sa.Column("codigo_hash", sa.String(64), nullable=False),
    )
    op.add_column(
        "cambio_contrasena_validaciones",
        sa.Column("intentos_fallidos", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    """Downgrade schema. Solo seguro con la tabla vacía (el código en claro no se puede recuperar)."""
    op.drop_column("cambio_contrasena_validaciones", "intentos_fallidos")
    op.drop_column("cambio_contrasena_validaciones", "codigo_hash")
    op.add_column(
        "cambio_contrasena_validaciones",
        sa.Column("codigo", sa.String(4), nullable=False),
    )
