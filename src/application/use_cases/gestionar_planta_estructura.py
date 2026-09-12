"""src/application/use_cases/gestionar_planta_estructura.py."""

from src.application.dtos.planta_estructura_dto import (
    GuardarLayoutRequestDTO,
    GuardarUnifilarRequestDTO,
    LayoutPlantaDTO,
    UnifilarPlantaDTO,
)
from src.application.mappers.planta_estructura_mapper import PlantaEstructuraMapper
from src.domain.telemetria.entities import Planta
from src.domain.telemetria.exceptions import PlantaNoEncontradaError
from src.domain.telemetria.ports import RepositorioOrganizacionesPort


class GestionarPlantaEstructuraUseCase:
    def __init__(self, repo_organizaciones: RepositorioOrganizacionesPort):
        self.repo_organizaciones = repo_organizaciones

    def _resolver_planta(self, planta_id: str | None = None, organizacion_id: str | None = None) -> Planta:
        if planta_id:
            planta = self.repo_organizaciones.obtener_planta_por_id(planta_id)
            if planta:
                return planta
            raise PlantaNoEncontradaError(f"Planta con id '{planta_id}' no encontrada.")

        plantas = self.repo_organizaciones.listar_plantas(organizacion_id)
        if plantas:
            return plantas[0]

        raise PlantaNoEncontradaError("No hay plantas registradas en la organización.")

    def obtener_unifilar(self, planta_id: str | None = None, organizacion_id: str | None = None) -> UnifilarPlantaDTO:
        planta = self._resolver_planta(planta_id, organizacion_id)
        nodos = self.repo_organizaciones.obtener_nodos_unifilar(planta.id)
        return UnifilarPlantaDTO(
            planta_id=planta.id,
            nombre_planta=planta.nombre,
            nodos=[PlantaEstructuraMapper.nodo_to_dto(n) for n in nodos],
        )

    def guardar_unifilar(self, planta_id: str, dto: GuardarUnifilarRequestDTO) -> UnifilarPlantaDTO:
        planta = self._resolver_planta(planta_id)
        nodos_entidades = [PlantaEstructuraMapper.dto_to_nodo(n, planta.id) for n in dto.nodos]
        guardados = self.repo_organizaciones.guardar_nodos_unifilar(planta.id, nodos_entidades)
        return UnifilarPlantaDTO(
            planta_id=planta.id,
            nombre_planta=planta.nombre,
            nodos=[PlantaEstructuraMapper.nodo_to_dto(n) for n in guardados],
        )

    def obtener_layout(self, planta_id: str | None = None, organizacion_id: str | None = None) -> LayoutPlantaDTO:
        planta = self._resolver_planta(planta_id, organizacion_id)
        zonas = self.repo_organizaciones.obtener_zonas_planta(planta.id)
        dispositivos = self.repo_organizaciones.obtener_dispositivos_layout(planta.id)
        return LayoutPlantaDTO(
            planta_id=planta.id,
            nombre_planta=planta.nombre,
            plano_svg_url=planta.layout_svg_url,
            zonas=[PlantaEstructuraMapper.zona_to_dto(z) for z in zonas],
            dispositivos=[PlantaEstructuraMapper.disp_layout_to_dto(d) for d in dispositivos],
        )

    def guardar_layout(self, planta_id: str, dto: GuardarLayoutRequestDTO) -> LayoutPlantaDTO:
        planta = self._resolver_planta(planta_id)
        zonas_entidades = [PlantaEstructuraMapper.dto_to_zona(z, planta.id) for z in dto.zonas]
        disp_entidades = [PlantaEstructuraMapper.dto_to_disp_layout(d, planta.id) for d in dto.dispositivos]

        self.repo_organizaciones.guardar_layout_planta(
            planta.id,
            dto.plano_svg_url,
            zonas_entidades,
            disp_entidades,
        )

        planta_actualizada = self._resolver_planta(planta_id)
        zonas_actualizadas = self.repo_organizaciones.obtener_zonas_planta(planta.id)
        disp_actualizados = self.repo_organizaciones.obtener_dispositivos_layout(planta.id)

        return LayoutPlantaDTO(
            planta_id=planta_actualizada.id,
            nombre_planta=planta_actualizada.nombre,
            plano_svg_url=planta_actualizada.layout_svg_url,
            zonas=[PlantaEstructuraMapper.zona_to_dto(z) for z in zonas_actualizadas],
            dispositivos=[PlantaEstructuraMapper.disp_layout_to_dto(d) for d in disp_actualizados],
        )
