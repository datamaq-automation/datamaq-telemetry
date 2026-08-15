import uuid

from src.application.dtos.plan_dto import PlanCreateDTO, PlanResponseDTO
from src.domain.telemetria.entities import PlanTelemetria


class PlanMapper:
    @staticmethod
    def to_dto(entity: PlanTelemetria) -> PlanResponseDTO:
        return PlanResponseDTO(
            id=entity.id,
            nombre=entity.nombre,
            descripcion=entity.descripcion,
            precio_mensual_ars=entity.precio_mensual_ars,
            visibilidad=entity.visibilidad,
            retencion_dias=entity.retencion_dias,
            granularidad_minutos=entity.granularidad_minutos,
            max_dispositivos=entity.max_dispositivos,
            canales_notificacion=list(entity.canales_notificacion),
            creado_en=entity.creado_en,
            actualizado_en=entity.actualizado_en,
        )

    @staticmethod
    def create_dto_to_entity(dto: PlanCreateDTO, id: str | None = None) -> PlanTelemetria:
        plan_id = id or str(uuid.uuid4())
        return PlanTelemetria(
            id=plan_id,
            nombre=dto.nombre,
            descripcion=dto.descripcion,
            precio_mensual_ars=dto.precio_mensual_ars,
            visibilidad=dto.visibilidad,
            retencion_dias=dto.retencion_dias,
            granularidad_minutos=dto.granularidad_minutos,
            max_dispositivos=dto.max_dispositivos,
            canales_notificacion=list(dto.canales_notificacion),
        )
