"""src/application/mappers/alerta_mapper.py."""

from src.application.dtos.alerta_dto import AlertaResponseDTO
from src.domain.telemetria.entities import AlertaDispositivo


class AlertaMapper:
    @staticmethod
    def to_dto(entity: AlertaDispositivo) -> AlertaResponseDTO:
        return AlertaResponseDTO(
            id=entity.id if entity.id is not None else 0,
            dispositivo_id=entity.dispositivo_id,
            tipo_alerta=entity.tipo_alerta,
            severidad=entity.severidad.value,
            mensaje=entity.mensaje,
            esta_resuelta=entity.esta_resuelta,
            disparada_en=entity.disparada_en,
            resuelta_en=entity.resuelta_en,
            fase=entity.fase,
            valor_medido=entity.valor_medido,
            valor_umbral=entity.valor_umbral,
            unidad=entity.unidad,
            categoria=entity.categoria,
            duracion_segundos=entity.duracion_segundos,
            observaciones=entity.observaciones,
        )
