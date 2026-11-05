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
from src.domain.telemetria.exceptions import (
    EstructuraUnifilarInvalidaError,
    PlantaNoEncontradaError,
)
from src.domain.telemetria.ports import RepositorioOrganizacionesPort
from src.domain.telemetria.servicios.arbol_unifilar import ArbolUnifilarService


class GestionarPlantaEstructuraUseCase:
    def __init__(
        self,
        repo_organizaciones: RepositorioOrganizacionesPort,
        repo_maquinas: RepositorioMaquinasPort | None = None,
    ) -> None:
        self.repo_organizaciones = repo_organizaciones
        self.repo_maquinas = repo_maquinas

    def _resolver_planta(self, planta_id: str | None = None, organizacion_id: str | None = None) -> Planta | None:
        """Sin id no hay planta: la activa la decide la política de acceso, no este caso de uso.

        Con `organizacion_id`, una planta de otra organización se trata como inexistente.
        """
        if not planta_id:
            return None
        planta = self.repo_organizaciones.obtener_planta_por_id(planta_id)
        if planta is None or (organizacion_id is not None and planta.organizacion_id != organizacion_id):
            raise PlantaNoEncontradaError(f"Planta con id '{planta_id}' no encontrada.")
        return planta

    def obtener_unifilar(self, planta_id: str | None = None, organizacion_id: str | None = None) -> UnifilarPlantaDTO:
        planta = self._resolver_planta(planta_id, organizacion_id)
        if planta is None:
            return UnifilarPlantaDTO(planta_id="", nombre_planta="", nodos=[])
        nodos = self.repo_organizaciones.obtener_nodos_unifilar(planta.id)
        nombres_maquina = self._nombres_maquina_por_dispositivo(planta, nodos)
        arbol = ArbolUnifilarService(nodos)
        try:
            arbol.validar()
            topologia_valida = True
        except EstructuraUnifilarInvalidaError:
            topologia_valida = False

        nodos_dto = []
        for n in nodos:
            pasante = n.es_pasante or (topologia_valida and arbol.es_nodo_pasante(n.id))
            nodos_dto.append(
                PlantaEstructuraMapper.nodo_to_dto(
                    n,
                    nombre_maquina=nombres_maquina.get(n.device_id or ""),
                    es_pasante=pasante,
                )
            )

        return UnifilarPlantaDTO(
            planta_id=planta.id,
            nombre_planta=planta.nombre,
            nodos=nodos_dto,
            topologia_valida=topologia_valida,
        )

    def _nombres_maquina_por_dispositivo(self, planta: Planta, nodos: list[NodoUnifilar]) -> dict[str, str]:
        """R-03: máquina 1:1 del medidor de cada nodo medido, en una sola consulta por planta."""
        if self.repo_maquinas is None or not any(n.device_id for n in nodos):
            return {}
        return {m.dispositivo_id: m.nombre for m in self.repo_maquinas.listar(planta.organizacion_id)}

    def obtener_layout(self, planta_id: str | None = None, organizacion_id: str | None = None) -> LayoutPlantaDTO:
        planta = self._resolver_planta(planta_id, organizacion_id)
        if planta is None:
            return LayoutPlantaDTO(planta_id="", nombre_planta="", plano_svg_url=None, zonas=[], dispositivos=[])
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
        if planta is None:
            return PlantaAreasEstadisticasResponseDTO(planta_id="", superficie_total_m2=None, areas=[])
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
