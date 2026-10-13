"""src/application/use_cases/gestionar_activos_unifilar.py — Caso de uso para gestionar activos unifilares mutables y jerarquía híbrida."""

import uuid

from src.application.dtos.activo_unifilar_dto import (
    ActivoUnifilarDTO,
    ActualizarActivoUnifilarDTO,
    CrearActivoUnifilarDTO,
    JerarquiaHibridaPlantaDTO,
)
from src.application.mappers.activo_unifilar_mapper import ActivoUnifilarMapper
from src.application.mappers.planta_estructura_mapper import PlantaEstructuraMapper
from src.domain.telemetria.entities import ahora_utc
from src.domain.telemetria.exceptions import ActivoUnifilarNoEncontradoError
from src.domain.telemetria.ports import RepositorioActivosUnifilarPort, RepositorioOrganizacionesPort
from src.domain.telemetria.value_objects import TipoActivoUnifilar


class GestionarActivosUnifilarUseCase:
    """Caso de uso para la administración y unificación del árbol unifilar híbrido."""

    def __init__(
        self,
        repo_activos: RepositorioActivosUnifilarPort,
        repo_organizaciones: RepositorioOrganizacionesPort | None = None,
    ) -> None:
        self.repo_activos = repo_activos
        self.repo_organizaciones = repo_organizaciones

    def crear_activo(self, dto: CrearActivoUnifilarDTO) -> ActivoUnifilarDTO:
        activo_id = dto.id.strip() if dto.id and dto.id.strip() else f"act_{uuid.uuid4().hex[:12]}"
        entidad = ActivoUnifilarMapper.to_entity(dto, activo_id)
        guardado = self.repo_activos.guardar(entidad)
        return ActivoUnifilarMapper.to_dto(guardado)

    def obtener_activo(self, activo_id: str) -> ActivoUnifilarDTO:
        activo = self.repo_activos.obtener_por_id(activo_id)
        if not activo:
            raise ActivoUnifilarNoEncontradoError(f"Activo unifilar con id '{activo_id}' no encontrado.")
        return ActivoUnifilarMapper.to_dto(activo)

    def listar_activos_planta(self, planta_id: str) -> list[ActivoUnifilarDTO]:
        activos = self.repo_activos.listar_por_planta(planta_id)
        return [ActivoUnifilarMapper.to_dto(a) for a in activos]

    def actualizar_activo(self, activo_id: str, dto: ActualizarActivoUnifilarDTO) -> ActivoUnifilarDTO:
        activo = self.repo_activos.obtener_por_id(activo_id)
        if not activo:
            raise ActivoUnifilarNoEncontradoError(f"Activo unifilar con id '{activo_id}' no encontrado.")

        if dto.nombre is not None:
            activo.nombre = dto.nombre
        if dto.tipo is not None:
            activo.tipo = TipoActivoUnifilar(dto.tipo)
        if dto.tension_nominal_v is not None:
            activo.tension_nominal_v = dto.tension_nominal_v
        if dto.parent_id is not None:
            activo.parent_id = dto.parent_id
        if dto.device_id is not None:
            activo.device_id = dto.device_id
        if dto.potencia_nominal_kw is not None:
            activo.potencia_nominal_kw = dto.potencia_nominal_kw
        if dto.capacidad_nominal_kva is not None:
            activo.capacidad_nominal_kva = dto.capacidad_nominal_kva
        if dto.categoria_uso is not None:
            activo.categoria_uso = dto.categoria_uso
        if dto.uso_significativo is not None:
            activo.uso_significativo = dto.uso_significativo
        if dto.posicion_x is not None:
            activo.posicion_x = dto.posicion_x
        if dto.posicion_y is not None:
            activo.posicion_y = dto.posicion_y
        if dto.ancho is not None:
            activo.ancho = dto.ancho
        if dto.alto is not None:
            activo.alto = dto.alto
        if dto.orden is not None:
            activo.orden = dto.orden

        activo.actualizado_en = ahora_utc()
        guardado = self.repo_activos.guardar(activo)
        return ActivoUnifilarMapper.to_dto(guardado)

    def eliminar_activo(self, activo_id: str) -> bool:
        return self.repo_activos.eliminar(activo_id)

    def obtener_jerarquia_hibrida(self, planta_id: str) -> JerarquiaHibridaPlantaDTO:
        nodos_inmutables = []
        if self.repo_organizaciones:
            nodos_raw = self.repo_organizaciones.obtener_nodos_unifilar(planta_id)
            nodos_inmutables = [PlantaEstructuraMapper.nodo_to_dto(n) for n in nodos_raw]

        activos = self.repo_activos.listar_por_planta(planta_id)
        activos_mutables = [ActivoUnifilarMapper.to_dto(a) for a in activos]

        nodos_mutables_como_unifilar = [ActivoUnifilarMapper.to_nodo_dto(a) for a in activos]

        ids_inmutables = {n.id for n in nodos_inmutables}
        nodos_unificados = list(nodos_inmutables)
        for nm in nodos_mutables_como_unifilar:
            if nm.id not in ids_inmutables:
                nodos_unificados.append(nm)

        return JerarquiaHibridaPlantaDTO(
            planta_id=planta_id,
            nodos_inmutables=nodos_inmutables,
            activos_mutables=activos_mutables,
            nodos_unificados=nodos_unificados,
        )
