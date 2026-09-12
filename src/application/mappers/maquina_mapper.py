"""src/application/mappers/maquina_mapper.py."""

from src.application.dtos.maquina_dto import MaquinaCreateDTO, MaquinaResponseDTO
from src.domain.disponibilidad.entities import Maquina


class MaquinaMapper:
    @staticmethod
    def to_dto(entity: Maquina) -> MaquinaResponseDTO:
        return MaquinaResponseDTO(
            id=entity.id,
            dispositivo_id=entity.dispositivo_id,
            nombre=entity.nombre,
            umbral_marcha_w=entity.umbral_marcha_w,
            ventana_persistencia_lecturas=entity.ventana_persistencia_lecturas,
            ventana_persistencia_segundos=entity.ventana_persistencia_segundos,
            esta_calibrada=entity.esta_calibrada,
            creado_en=entity.creado_en,
            actualizado_en=entity.actualizado_en,
        )

    @staticmethod
    def create_dto_to_entity(dto: MaquinaCreateDTO, id_str: str) -> Maquina:
        return Maquina(
            id=id_str,
            dispositivo_id=dto.dispositivo_id,
            nombre=dto.nombre,
        )
