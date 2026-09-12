"""add assistant conversation/message/intent tables

Revision ID: j4k5l6m7n8o9
Revises: i3j4k5l6m7n8
Create Date: 2026-09-13 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "j4k5l6m7n8o9"
down_revision: str | Sequence[str] | None = "i3j4k5l6m7n8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table("assistant_conversations"):
        op.create_table(
            "assistant_conversations",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
            ),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("idx_assistant_conversations_org", "assistant_conversations", ["organization_id"])

    if not inspector.has_table("assistant_messages"):
        op.create_table(
            "assistant_messages",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "conversation_id",
                sa.String(36),
                sa.ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("role", sa.String(20), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index(
            "idx_assistant_messages_conversation", "assistant_messages", ["conversation_id", "created_at"]
        )

    if not inspector.has_table("assistant_intent_classifications"):
        op.create_table(
            "assistant_intent_classifications",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "message_id", sa.String(36), sa.ForeignKey("assistant_messages.id", ondelete="CASCADE"), nullable=False
            ),
            sa.Column("intent_name", sa.String(100), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("classified_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index(
            "idx_assistant_intent_classifications_message", "assistant_intent_classifications", ["message_id"]
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("assistant_intent_classifications"):
        op.drop_table("assistant_intent_classifications")
    if inspector.has_table("assistant_messages"):
        op.drop_table("assistant_messages")
    if inspector.has_table("assistant_conversations"):
        op.drop_table("assistant_conversations")
