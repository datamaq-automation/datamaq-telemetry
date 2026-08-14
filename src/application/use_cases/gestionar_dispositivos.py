import uuid

from src.application.dtos.dispositivo_dto import (
    DispositivoCreateDTO,
    DispositivoResponseDTO,
    DispositivoUpdateDTO,
)
from src.application.dtos.organizacion_dto import (
    OrganizacionCreateDTO,
    OrganizacionResponseDTO,
    PlantaCreateDTO,
    PlantaResponseDTO,
)
from src.application.mappers.dispositivo_mapper import (
    DispositivoMapper,
    OrganizacionMapper,
)
from src.domain.telemetria.entities import Organizacion, Planta
from src.domain.telemetria.exceptions import DispositivoNoEncontradoError
from src.domain.telemetria.ports import (
    RepositorioDispositivosPort,
    RepositorioOrganizacionesPort,
)
from src.domain.telemetria.value_objects import MacAddress


class GestionarDispositivosUseCase:
    def __init__(
        self,
        repo_dispositivos: RepositorioDispositivosPort,
        repo_organizaciones: RepositorioOrganizacionesPort,
    ):
        self.repo_dispositivos = repo_dispositivos
        self.repo_organizaciones = repo_organizaciones

    def listar_dispositivos(self, planta_id: str | None = None) -> list[DispositivoResponseDTO]:
        dispositivos = self.repo_dispositivos.listar(planta_id)
        return [DispositivoMapper.to_dto(d) for d in dispositivos]

    def obtener_dispositivo(self, id_o_uid: str) -> DispositivoResponseDTO:
        dev = self.repo_dispositivos.obtener_por_id(id_o_uid)
        if not dev:
            try:
                mac_vo = MacAddress(id_o_uid)
                dev = self.repo_dispositivos.obtener_por_uid(mac_vo)
            except Exception:
                pass
        if not dev:
            raise DispositivoNoEncontradoError(f"Dispositivo '{id_o_uid}' no encontrado.")
        return DispositivoMapper.to_dto(dev)

    def registrar_dispositivo(self, dto: DispositivoCreateDTO) -> DispositivoResponseDTO:
        entity = DispositivoMapper.create_dto_to_entity(dto, str(uuid.uuid4()))
        saved = self.repo_dispositivos.guardar(entity)
        return DispositivoMapper.to_dto(saved)

    def actualizar_dispositivo(self, id_o_uid: str, dto: DispositivoUpdateDTO) -> DispositivoResponseDTO:
        dev = self.repo_dispositivos.obtener_por_id(id_o_uid)
        if not dev:
            try:
                mac_vo = MacAddress(id_o_uid)
                dev = self.repo_dispositivos.obtener_por_uid(mac_vo)
            except Exception:
                pass
        if not dev:
            raise DispositivoNoEncontradoError(f"Dispositivo '{id_o_uid}' no encontrado.")

        if dto.nombre is not None:
            dev.nombre = dto.nombre
        if dto.planta_id is not None:
            dev.planta_id = dto.planta_id
        if dto.ubicacion_tag is not None:
            dev.ubicacion_tag = dto.ubicacion_tag
        if dto.esta_activo is not None:
            dev.esta_activo = dto.esta_activo

        saved = self.repo_dispositivos.guardar(dev)
        return DispositivoMapper.to_dto(saved)

    def listar_organizaciones(self) -> list[OrganizacionResponseDTO]:
        orgs = self.repo_organizaciones.listar_organizaciones()
        return [OrganizacionMapper.org_to_dto(o) for o in orgs]

    def crear_organizacion(self, dto: OrganizacionCreateDTO) -> OrganizacionResponseDTO:
        entity = Organizacion(
            id=str(uuid.uuid4()),
            nombre=dto.nombre,
            cuit=dto.cuit,
            email_contacto=dto.email_contacto,
            telefono_contacto=dto.telefono_contacto,
        )
        saved = self.repo_organizaciones.guardar_organizacion(entity)
        return OrganizacionMapper.org_to_dto(saved)

    def listar_plantas(self, organizacion_id: str | None = None) -> list[PlantaResponseDTO]:
        plantas = self.repo_organizaciones.listar_plantas(organizacion_id)
        return [OrganizacionMapper.planta_to_dto(p) for p in plantas]

    def crear_planta(self, dto: PlantaCreateDTO) -> PlantaResponseDTO:
        entity = Planta(
            id=str(uuid.uuid4()),
            organizacion_id=dto.organizacion_id,
            nombre=dto.nombre,
            direccion=dto.direccion,
            latitud=dto.latitud,
            longitud=dto.longitud,
        )
        saved = self.repo_organizaciones.guardar_planta(entity)
        return OrganizacionMapper.planta_to_dto(saved)
