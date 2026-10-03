"""src/infrastructure/sqlalchemy/repositories/asistente_repository.py."""

from datetime import datetime

from sqlalchemy.orm import Session

from src.domain.asistente.entities import (
    ConversacionAsistente,
    MensajeAsistente,
    RegistroClasificacionIntencion,
)
from src.domain.asistente.ports import RepositorioConversacionesAsistentePort
from src.infrastructure.sqlalchemy.models import generate_uuid
from src.infrastructure.sqlalchemy.models_asistente import (
    AssistantConversationModel,
    AssistantIntentClassificationModel,
    AssistantMessageModel,
    AuditAsistenteConsentimientoModel,
)


class MySQLConversacionesAsistenteRepository(RepositorioConversacionesAsistentePort):
    def __init__(self, db: Session):
        self.db = db

    def _conversacion_a_entidad(self, model: AssistantConversationModel) -> ConversacionAsistente:
        return ConversacionAsistente(
            id=model.id,
            organizacion_id=model.organization_id,
            usuario_id=model.user_id,
            creado_en=model.created_at,
            actualizado_en=model.updated_at,
        )

    def _mensaje_a_entidad(self, model: AssistantMessageModel) -> MensajeAsistente:
        return MensajeAsistente(
            id=model.id,
            conversacion_id=model.conversation_id,
            rol=model.role,  # type: ignore[arg-type]
            texto=model.text,
            creado_en=model.created_at,
        )

    def crear_conversacion(self, organizacion_id: str, usuario_id: str) -> ConversacionAsistente:
        model = AssistantConversationModel(
            id=generate_uuid(),
            organization_id=organizacion_id,
            user_id=usuario_id,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return self._conversacion_a_entidad(model)

    def obtener_conversacion(self, conversacion_id: str, organizacion_id: str) -> ConversacionAsistente | None:
        model = (
            self.db.query(AssistantConversationModel)
            .filter(
                AssistantConversationModel.id == conversacion_id,
                AssistantConversationModel.organization_id == organizacion_id,
            )
            .first()
        )
        return self._conversacion_a_entidad(model) if model else None

    def listar_mensajes(self, conversacion_id: str, organizacion_id: str) -> list[MensajeAsistente]:
        conversacion_valida = (
            self.db.query(AssistantConversationModel.id)
            .filter(
                AssistantConversationModel.id == conversacion_id,
                AssistantConversationModel.organization_id == organizacion_id,
            )
            .first()
        )
        if conversacion_valida is None:
            return []

        models = (
            self.db.query(AssistantMessageModel)
            .filter(AssistantMessageModel.conversation_id == conversacion_id)
            .order_by(AssistantMessageModel.created_at.asc())
            .all()
        )
        return [self._mensaje_a_entidad(m) for m in models]

    def guardar_mensaje(self, mensaje: MensajeAsistente, organizacion_id: str) -> None:
        conversacion_valida = (
            self.db.query(AssistantConversationModel.id)
            .filter(
                AssistantConversationModel.id == mensaje.conversacion_id,
                AssistantConversationModel.organization_id == organizacion_id,
            )
            .first()
        )
        if conversacion_valida is None:
            raise ValueError("La conversación no existe o no pertenece a la organización indicada")

        model = AssistantMessageModel(
            id=mensaje.id,
            conversation_id=mensaje.conversacion_id,
            role=mensaje.rol,
            text=mensaje.texto,
            created_at=mensaje.creado_en,
        )
        self.db.add(model)
        self.db.commit()

    def guardar_clasificacion(self, registro: RegistroClasificacionIntencion, organizacion_id: str) -> None:
        mensaje_valido = (
            self.db.query(AssistantMessageModel.id)
            .join(AssistantConversationModel, AssistantConversationModel.id == AssistantMessageModel.conversation_id)
            .filter(
                AssistantMessageModel.id == registro.mensaje_id,
                AssistantConversationModel.organization_id == organizacion_id,
            )
            .first()
        )
        if mensaje_valido is None:
            raise ValueError("El mensaje no existe o no pertenece a la organización indicada")

        model = AssistantIntentClassificationModel(
            id=registro.id,
            message_id=registro.mensaje_id,
            intent_name=registro.intencion.nombre,
            confidence=registro.intencion.confianza,
            classified_at=registro.clasificado_en,
        )
        self.db.add(model)
        self.db.commit()


class MySQLAsistenteConsentimientoRepository:
    """Repository para auditoría de consentimiento a envío de datos a Groq."""

    def __init__(self, db: Session):
        self.db = db

    def guardar_consentimiento(
        self,
        usuario_id: str,
        organizacion_id: str,
        consentimiento_otorgado: bool,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> str:
        """Guardar registro de consentimiento y retornar su ID."""
        model = AuditAsistenteConsentimientoModel(
            id=generate_uuid(),
            usuario_id=usuario_id,
            organizacion_id=organizacion_id,
            consentimiento_otorgado=consentimiento_otorgado,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return model.id

    def obtener_consentimiento_mas_reciente(self, usuario_id: str) -> bool | None:
        """Obtener el consentimiento más reciente de un usuario, o None si no hay registro."""
        model = (
            self.db.query(AuditAsistenteConsentimientoModel)
            .filter(AuditAsistenteConsentimientoModel.usuario_id == usuario_id)
            .order_by(AuditAsistenteConsentimientoModel.fecha.desc())
            .first()
        )
        return model.consentimiento_otorgado if model else None

    def listar_consentimientos_organizacion(
        self, organizacion_id: str, limit: int = 100
    ) -> list[dict[str, str | bool | datetime | None]]:
        """Listar consentimientos de una organización para auditoría."""
        models = (
            self.db.query(AuditAsistenteConsentimientoModel)
            .filter(AuditAsistenteConsentimientoModel.organizacion_id == organizacion_id)
            .order_by(AuditAsistenteConsentimientoModel.fecha.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": m.id,
                "usuario_id": m.usuario_id,
                "consentimiento_otorgado": m.consentimiento_otorgado,
                "fecha": m.fecha,
                "ip_address": m.ip_address,
                "user_agent": m.user_agent,
            }
            for m in models
        ]
