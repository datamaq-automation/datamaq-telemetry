"""src/infrastructure/sqlalchemy/repositories/planes_repository.py."""

from decimal import Decimal

from sqlalchemy.orm import Session

from src.domain.telemetria.entities import PlanTelemetria
from src.domain.telemetria.ports import RepositorioPlanesPort
from src.domain.telemetria.value_objects import VisibilidadPlan
from src.infrastructure.sqlalchemy.models import PlanModel


class MySQLPlanesRepository(RepositorioPlanesPort):
    def __init__(self, db: Session):
        self.db = db

    def _to_entity(self, model: PlanModel) -> PlanTelemetria:
        return PlanTelemetria(
            id=model.id,
            nombre=model.name,
            descripcion=model.description,
            precio_mensual_ars=Decimal(str(model.monthly_price_ars)),
            visibilidad=VisibilidadPlan(model.visibility)
            if model.visibility in VisibilidadPlan._value2member_map_
            else VisibilidadPlan.PUBLICO,
            retencion_dias=model.retention_days,
            granularidad_minutos=model.granularity_minutes,
            max_dispositivos=model.max_devices,
            canales_notificacion=list(model.notification_channels or []),
            creado_en=model.created_at,
            actualizado_en=model.updated_at,
        )

    def listar_planes(self) -> list[PlanTelemetria]:
        models = self.db.query(PlanModel).all()
        return [self._to_entity(m) for m in models]

    def obtener_por_id(self, plan_id: str) -> PlanTelemetria | None:
        model = self.db.query(PlanModel).filter(PlanModel.id == plan_id).first()
        if not model:
            return None
        return self._to_entity(model)

    def guardar_plan(self, plan: PlanTelemetria) -> PlanTelemetria:
        model = self.db.query(PlanModel).filter(PlanModel.id == plan.id).first()
        if not model:
            model = PlanModel(
                id=plan.id,
                name=plan.nombre,
                description=plan.descripcion,
                monthly_price_ars=plan.precio_mensual_ars,
                visibility=plan.visibilidad.value,
                retention_days=plan.retencion_dias,
                granularity_minutes=plan.granularidad_minutos,
                max_devices=plan.max_dispositivos,
                notification_channels=plan.canales_notificacion,
            )
            self.db.add(model)
        else:
            model.name = plan.nombre
            model.description = plan.descripcion
            model.monthly_price_ars = plan.precio_mensual_ars
            model.visibility = plan.visibilidad.value
            model.retention_days = plan.retencion_dias
            model.granularity_minutes = plan.granularidad_minutos
            model.max_devices = plan.max_dispositivos
            model.notification_channels = plan.canales_notificacion

        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)
