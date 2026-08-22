from src.application.dtos.dispositivo_dto import (
    DispositivoCreateDTO,
    DispositivoResponseDTO,
)
from src.application.dtos.organizacion_dto import (
    OrganizacionResponseDTO,
    PlantaResponseDTO,
)
from src.domain.telemetria.entities import Dispositivo, Organizacion, Planta
from src.domain.telemetria.value_objects import EstadoDispositivo, MacAddress


class DispositivoMapper:
    @staticmethod
    def to_dto(entity: Dispositivo) -> DispositivoResponseDTO:
        return DispositivoResponseDTO(
            id=entity.id,
            device_uid=entity.device_uid.valor,
            nombre=entity.nombre,
            modelo=entity.modelo,
            planta_id=entity.planta_id,
            numero_serie=entity.numero_serie,
            version_hw=entity.version_hw,
            version_fw=entity.version_fw,
            ubicacion_tag=entity.ubicacion_tag,
            esta_activo=entity.esta_activo,
            tipo_instalacion=entity.tipo_instalacion,
            fases_con_ti=entity.fases_con_ti,
            estado=entity.estado.value,
            visto_por_ultima_vez=entity.visto_por_ultima_vez,
            creado_en=entity.creado_en,
            actualizado_en=entity.actualizado_en,
            voltage_linea_V=getattr(entity, "voltage_linea_V", None),
        )

    @staticmethod
    def create_dto_to_entity(dto: DispositivoCreateDTO, id_str: str) -> Dispositivo:
        return Dispositivo(
            id=id_str,
            device_uid=MacAddress(dto.device_uid),
            nombre=dto.nombre,
            modelo=dto.modelo,
            planta_id=dto.planta_id,
            numero_serie=dto.numero_serie,
            version_hw=dto.version_hw,
            version_fw=dto.version_fw,
            ubicacion_tag=dto.ubicacion_tag,
            esta_activo=dto.esta_activo,
            tipo_instalacion=dto.tipo_instalacion or "CONSUMO",
            fases_con_ti=dto.fases_con_ti or "R,S,T",
            estado=EstadoDispositivo.ONLINE,
        )


class OrganizacionMapper:
    @staticmethod
    def org_to_dto(entity: Organizacion) -> OrganizacionResponseDTO:
        return OrganizacionResponseDTO(
            id=entity.id,
            nombre=entity.nombre,
            plan_id=entity.plan_id,
            cuit=entity.cuit,
            email_contacto=entity.email_contacto,
            telefono_contacto=entity.telefono_contacto,
            creado_en=entity.creado_en,
            actualizado_en=entity.actualizado_en,
        )

    @staticmethod
    def planta_to_dto(entity: Planta) -> PlantaResponseDTO:
        return PlantaResponseDTO(
            id=entity.id,
            organizacion_id=entity.organizacion_id,
            nombre=entity.nombre,
            direccion=entity.direccion,
            latitud=entity.latitud,
            longitud=entity.longitud,
            creado_en=entity.creado_en,
            actualizado_en=entity.actualizado_en,
        )
