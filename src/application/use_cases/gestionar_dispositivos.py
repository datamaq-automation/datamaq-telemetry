"""src/application/use_cases/gestionar_dispositivos.py."""

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
from src.domain.telemetria.entities import Dispositivo, Organizacion, Planta
from src.domain.telemetria.exceptions import (
    DispositivoNoEncontradoError,
    LimiteDispositivosExcedidoError,
)
from src.domain.telemetria.ports import (
    RepositorioDispositivosPort,
    RepositorioOrganizacionesPort,
    RepositorioPlanesPort,
)
from src.domain.telemetria.value_objects import MacAddress, ModoFreeTier


class GestionarDispositivosUseCase:
    def __init__(
        self,
        repo_dispositivos: RepositorioDispositivosPort,
        repo_organizaciones: RepositorioOrganizacionesPort,
        repo_planes: RepositorioPlanesPort | None = None,
    ):
        self.repo_dispositivos = repo_dispositivos
        self.repo_organizaciones = repo_organizaciones
        self.repo_planes = repo_planes

    def _validar_cupo_dispositivos(self, planta_id: str) -> None:
        if not self.repo_planes:
            return
        planta = self.repo_organizaciones.obtener_planta_por_id(planta_id)
        if not planta:
            return
        org = self.repo_organizaciones.obtener_por_id(planta.organizacion_id)
        if not org:
            return
        plan = self.repo_planes.obtener_por_id(org.plan_id) if org.plan_id else None
        max_permitido = plan.max_dispositivos if plan else 1
        actual = self.repo_dispositivos.contar_por_organizacion(org.id)
        if actual >= max_permitido:
            raise LimiteDispositivosExcedidoError(
                f"La organización '{org.nombre}' alcanzó el límite de {max_permitido} dispositivos permitidos por su plan."
            )

    def _enriquecer_dispositivo(self, dev: Dispositivo) -> DispositivoResponseDTO:
        area_id = None
        linea_id = None
        if dev.planta_id and self.repo_organizaciones:
            try:
                disps_layout = self.repo_organizaciones.obtener_dispositivos_layout(dev.planta_id)
                d_layout = next(
                    (d for d in disps_layout if d.device_id in (dev.id, dev.device_uid.valor)),
                    None,
                )
                if d_layout:
                    area_id = d_layout.zona_id
            except Exception:
                pass

            try:
                nodos = self.repo_organizaciones.obtener_nodos_unifilar(dev.planta_id)
                nodo = next(
                    (n for n in nodos if n.device_id in (dev.id, dev.device_uid.valor)),
                    None,
                )
                if nodo:
                    linea_id = nodo.parent_id or nodo.id
            except Exception:
                pass

        return DispositivoMapper.to_dto(dev, area_id=area_id, linea_id=linea_id)

    def listar_dispositivos(
        self, planta_id: str | None = None, organizacion_id: str | None = None
    ) -> list[DispositivoResponseDTO]:
        dispositivos = self.repo_dispositivos.listar(planta_id, organizacion_id=organizacion_id)
        return [self._enriquecer_dispositivo(d) for d in dispositivos]

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
        return self._enriquecer_dispositivo(dev)

    def registrar_dispositivo(self, dto: DispositivoCreateDTO) -> DispositivoResponseDTO:
        if dto.planta_id:
            self._validar_cupo_dispositivos(dto.planta_id)
        entity = DispositivoMapper.create_dto_to_entity(dto, str(uuid.uuid4()))
        saved = self.repo_dispositivos.guardar(entity)
        return self._enriquecer_dispositivo(saved)

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

        if dto.planta_id is not None and dto.planta_id != dev.planta_id:
            self._validar_cupo_dispositivos(dto.planta_id)
            dev.planta_id = dto.planta_id
        if dto.nombre is not None:
            dev.nombre = dto.nombre
        if dto.ubicacion_tag is not None:
            dev.ubicacion_tag = dto.ubicacion_tag
        if dto.numero_serie is not None:
            dev.numero_serie = dto.numero_serie
        if dto.tipo_instalacion is not None:
            dev.tipo_instalacion = dto.tipo_instalacion
        if dto.fases_con_ti is not None:
            dev.fases_con_ti = dto.fases_con_ti
        if dto.categoria_tarifaria is not None:
            dev.categoria_tarifaria = dto.categoria_tarifaria
        if dto.penalizacion_reactiva_aplica is not None:
            dev.penalizacion_reactiva_aplica = dto.penalizacion_reactiva_aplica
        if dto.esta_activo is not None:
            dev.esta_activo = dto.esta_activo

        saved = self.repo_dispositivos.guardar(dev)
        return self._enriquecer_dispositivo(saved)

    def listar_organizaciones(self) -> list[OrganizacionResponseDTO]:
        orgs = self.repo_organizaciones.listar_organizaciones()
        return [OrganizacionMapper.org_to_dto(o) for o in orgs]

    def crear_organizacion(self, dto: OrganizacionCreateDTO) -> OrganizacionResponseDTO:
        modo_free_vo = (
            ModoFreeTier(dto.modo_free)
            if dto.modo_free in [m.value for m in ModoFreeTier]
            else ModoFreeTier.PRIVADO_BASICO
        )
        entity = Organizacion(
            id=str(uuid.uuid4()),
            nombre=dto.nombre,
            plan_id=dto.plan_id,
            cuit=dto.cuit,
            email_contacto=dto.email_contacto,
            telefono_contacto=dto.telefono_contacto,
            pro_vence_en=dto.pro_vence_en,
            modo_free=modo_free_vo,
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
