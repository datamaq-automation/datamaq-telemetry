"""src/application/use_cases/gestionar_planta_estructura.py."""

from src.application.dtos.planta_estructura_dto import (
    AreaEstadisticasDTO,
    CoordenadasZonaDTO,
    LayoutPlantaDTO,
    PlantaAreasEstadisticasResponseDTO,
    UnifilarPlantaDTO,
)
from src.application.mappers.planta_estructura_mapper import PlantaEstructuraMapper
from src.domain.disponibilidad.ports import RepositorioMaquinasPort
from src.domain.telemetria.entities import NodoUnifilar, Planta
from src.domain.telemetria.exceptions import PlantaNoEncontradaError
from src.domain.telemetria.ports import RepositorioOrganizacionesPort


class GestionarPlantaEstructuraUseCase:
    def __init__(
        self,
        repo_organizaciones: RepositorioOrganizacionesPort,
        repo_maquinas: RepositorioMaquinasPort | None = None,
    ):
        self.repo_organizaciones = repo_organizaciones
        self.repo_maquinas = repo_maquinas

    def _resolver_planta(self, planta_id: str | None = None, organizacion_id: str | None = None) -> Planta:
        if planta_id:
            planta = self.repo_organizaciones.obtener_planta_por_id(planta_id)
            if planta:
                return planta
            raise PlantaNoEncontradaError(f"Planta con id '{planta_id}' no encontrada.")

        plantas = self.repo_organizaciones.listar_plantas(organizacion_id)
        if plantas:
            return plantas[0]
        raise PlantaNoEncontradaError("No se encontraron plantas configuradas.")

    def obtener_unifilar(self, planta_id: str | None = None, organizacion_id: str | None = None) -> UnifilarPlantaDTO:
        planta = self._resolver_planta(planta_id, organizacion_id)
        nodos = self.repo_organizaciones.obtener_nodos_unifilar(planta.id)
        nombres_maquina = self._nombres_maquina_por_dispositivo(planta, nodos)
        return UnifilarPlantaDTO(
            planta_id=planta.id,
            nombre_planta=planta.nombre,
            nodos=[PlantaEstructuraMapper.nodo_to_dto(n, nombres_maquina.get(n.device_id or "")) for n in nodos],
        )

    def _nombres_maquina_por_dispositivo(self, planta: Planta, nodos: list[NodoUnifilar]) -> dict[str, str]:
        """R-03: máquina 1:1 del medidor de cada nodo medido, en una sola consulta por planta."""
        if self.repo_maquinas is None or not any(n.device_id for n in nodos):
            return {}
        return {m.dispositivo_id: m.nombre for m in self.repo_maquinas.listar(planta.organizacion_id)}

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

    def obtener_areas_estadisticas(
        self, planta_id: str | None = None, organizacion_id: str | None = None
    ) -> PlantaAreasEstadisticasResponseDTO:
        planta = self._resolver_planta(planta_id, organizacion_id)
        zonas = self.repo_organizaciones.obtener_zonas_planta(planta.id)
        dispositivos = self.repo_organizaciones.obtener_dispositivos_layout(planta.id)
        nodos = self.repo_organizaciones.obtener_nodos_unifilar(planta.id)

        nodos_por_device = {n.device_id: n for n in nodos if n.device_id}

        disp_por_zona: dict[str, list] = {}
        for d in dispositivos:
            if d.zona_id:
                disp_por_zona.setdefault(d.zona_id, []).append(d)

        areas_dtos: list[AreaEstadisticasDTO] = []
        for z in zonas:
            disps_zona = disp_por_zona.get(z.id, [])
            total_disps = len(disps_zona)
            potencia_total_kw = 0.0
            for d in disps_zona:
                nodo = nodos_por_device.get(d.device_id)
                if nodo and nodo.potencia_nominal_kw:
                    potencia_total_kw += nodo.potencia_nominal_kw

            coords_dto = (
                CoordenadasZonaDTO(
                    x_porcentaje=z.coordenadas.x_porcentaje,
                    y_porcentaje=z.coordenadas.y_porcentaje,
                    ancho_porcentaje=z.coordenadas.ancho_porcentaje,
                    alto_porcentaje=z.coordenadas.alto_porcentaje,
                )
                if z.coordenadas
                else None
            )

            sup_m2 = getattr(z, "superficie_m2", None)
            disp_ids = [d.device_id for d in disps_zona if d.device_id]
            areas_dtos.append(
                AreaEstadisticasDTO(
                    area_id=z.id,
                    nombre=z.nombre,
                    superficie_m2=sup_m2,
                    lineas_count=1 if total_disps > 0 else 0,
                    dispositivos_activos_count=total_disps,
                    dispositivos_total_count=total_disps,
                    carga_promedio_kw=round(potencia_total_kw, 2),
                    dispositivo_ids=disp_ids,
                    coordenadas_layout=coords_dto,
                )
            )

        sups = [a.superficie_m2 for a in areas_dtos if a.superficie_m2 is not None]
        return PlantaAreasEstadisticasResponseDTO(
            planta_id=planta.id,
            superficie_total_m2=sum(sups) if sups else None,
            areas=areas_dtos,
        )
