"""src/application/mappers/disponibilidad_mapper.py."""
from src.application.dtos.disponibilidad_dto import (
    EventoDisponibilidadResponseDTO,
    ParadaProgramadaResponseDTO,
)
from src.domain.disponibilidad.entities import EventoDisponibilidad, ParadaProgramada


class EventoDisponibilidadMapper:
    @staticmethod
    def to_dto(entity: EventoDisponibilidad) -> EventoDisponibilidadResponseDTO:
        return EventoDisponibilidadResponseDTO(
            id=entity.id if entity.id is not None else 0,
            maquina_id=entity.maquina_id,
            estado=entity.estado.value,
            tipo_parada=entity.tipo_parada.value if entity.tipo_parada else None,
            inicio_at=entity.inicio_at,
            fin_at=entity.fin_at,
            potencia_promedio_w=entity.potencia_promedio_w,
            origen=entity.origen.value,
            corregido_por_usuario_id=entity.corregido_por_usuario_id,
            corregido_at=entity.corregido_at,
            comentario=entity.comentario,
            duracion_segundos=entity.duracion_segundos,
        )


class ParadaProgramadaMapper:
    @staticmethod
    def to_dto(entity: ParadaProgramada) -> ParadaProgramadaResponseDTO:
        return ParadaProgramadaResponseDTO(
            id=entity.id,
            maquina_id=entity.maquina_id,
            inicio_at=entity.inicio_at,
            fin_at=entity.fin_at,
            motivo=entity.motivo,
            creado_por_usuario_id=entity.creado_por_usuario_id,
            creado_en=entity.creado_en,
        )
