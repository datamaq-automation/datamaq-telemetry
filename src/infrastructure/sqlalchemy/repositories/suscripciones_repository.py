"""src/infrastructure/sqlalchemy/repositories/suscripciones_repository.py."""

from sqlalchemy.orm import Session

from src.domain.telemetria.entities import Suscripcion
from src.domain.telemetria.ports import RepositorioSuscripcionesPort
from src.domain.telemetria.value_objects import ModoFreeTier
from src.infrastructure.sqlalchemy.models import OrganizationModel


class MySQLSuscripcionesRepository(RepositorioSuscripcionesPort):
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _to_entity(m: OrganizationModel) -> Suscripcion:
        try:
            modo_free = ModoFreeTier(m.free_tier_mode)
        except ValueError:
            modo_free = ModoFreeTier.PRIVADO_BASICO
        return Suscripcion(
            organizacion_id=m.id,
            plan_id=m.plan_id,
            pro_vence_en=m.pro_expires_at,
            modo_free=modo_free,
            actualizado_en=m.updated_at,
        )

    def obtener_por_organizacion(self, organizacion_id: str) -> Suscripcion | None:
        m = self.db.query(OrganizationModel).filter(OrganizationModel.id == organizacion_id).first()
        return self._to_entity(m) if m else None

    def guardar(self, suscripcion: Suscripcion) -> Suscripcion:
        m = self.db.query(OrganizationModel).filter(OrganizationModel.id == suscripcion.organizacion_id).first()
        if m is None:
            m = OrganizationModel(id=suscripcion.organizacion_id)
            self.db.add(m)
        m.plan_id = suscripcion.plan_id
        m.pro_expires_at = suscripcion.pro_vence_en
        m.free_tier_mode = suscripcion.modo_free.value
        self.db.commit()
        self.db.refresh(m)
        return self._to_entity(m)
