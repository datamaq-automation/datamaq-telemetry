"""src/infrastructure/sqlalchemy/models_asistente.py — Modelos del bounded context asistente.

Viven aparte de `models.py` por la misma razón que `models_cargas.py`: no empujar ese
archivo contra el límite de `scripts/verify_code_size.py`. Comparten la misma `Base`, así
que `alembic/env.py` tiene que importar este módulo para que la metadata los vea.
"""

from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.sqlalchemy.models import Base, ahora_utc, generate_uuid
from src.infrastructure.sqlalchemy.types import UtcDateTime


class AssistantConversationModel(Base):
    """Hilo de conversación entre un usuario y el asistente, acotado a una organización."""

    __tablename__ = "assistant_conversations"
    __table_args__ = (Index("idx_assistant_conversations_org", "organization_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, onupdate=ahora_utc, nullable=False)


class AssistantMessageModel(Base):
    """Un mensaje individual (de usuario o del asistente) dentro de una conversación."""

    __tablename__ = "assistant_messages"
    __table_args__ = (Index("idx_assistant_messages_conversation", "conversation_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assistant_conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)


class AssistantIntentClassificationModel(Base):
    """Historial de clasificación de intención de un mensaje de usuario, para auditoría/mejora."""

    __tablename__ = "assistant_intent_classifications"
    __table_args__ = (Index("idx_assistant_intent_classifications_message", "message_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    message_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assistant_messages.id", ondelete="CASCADE"), nullable=False
    )
    intent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    classified_at: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)
