"""src/application/mappers/planta_estructura_mapper.py."""

import uuid

from src.application.dtos.planta_estructura_dto import (
    CoordenadasZonaDTO,
    DispositivoLayoutDTO,
    LayoutPlantaDTO,
    NodoUnifilarDTO,
    PosicionLayoutDTO,
    UnifilarPlantaDTO,
    ZonaPlantaDTO,
)
from src.domain.telemetria.entities import (
    DispositivoLayout,
    LayoutPlanta,
    NodoUnifilar,
    UnifilarPlanta,
    ZonaPlanta,
)
from src.domain.telemetria.value_objects import (
    CoordenadasZona,
    PosicionLayout,
    TipoNodoUnifilar,
)


class PlantaEstructuraMapper:
    @staticmethod
    def nodo_to_dto(entity: NodoUnifilar) -> NodoUnifilarDTO:
        tipo_val = entity.tipo.value if hasattr(entity.tipo, "value") else str(entity.tipo)
        return NodoUnifilarDTO(
            id=entity.id,
            parent_id=entity.parent_id,
            nombre=entity.nombre,
            tipo=tipo_val,
            device_id=entity.device_id,
            tension_nominal_V=entity.tension_nominal_v,
            capacidad_nominal_kVA=entity.capacidad_nominal_kva,
            potencia_nominal_kw=entity.potencia_nominal_kw,
            uso_significativo=entity.uso_significativo,
            categoria_uso=entity.categoria_uso,
            variable_relevante=entity.variable_relevante,
            orden=entity.orden,
        )

    @staticmethod
    def dto_to_nodo(dto: NodoUnifilarDTO, planta_id: str) -> NodoUnifilar:
        tipo_enum = (
            TipoNodoUnifilar(dto.tipo) if dto.tipo in [t.value for t in TipoNodoUnifilar] else TipoNodoUnifilar.CARGA
        )
        return NodoUnifilar(
            id=dto.id or str(uuid.uuid4()),
            planta_id=planta_id,
            parent_id=dto.parent_id,
            nombre=dto.nombre,
            tipo=tipo_enum,
            device_id=dto.device_id,
            tension_nominal_v=dto.tension_nominal_V,
            capacidad_nominal_kva=dto.capacidad_nominal_kVA,
            potencia_nominal_kw=dto.potencia_nominal_kw,
            uso_significativo=dto.uso_significativo,
            categoria_uso=dto.categoria_uso,
            variable_relevante=dto.variable_relevante,
            orden=dto.orden,
        )

    @staticmethod
    def zona_to_dto(entity: ZonaPlanta) -> ZonaPlantaDTO:
        return ZonaPlantaDTO(
            id=entity.id,
            nombre=entity.nombre,
            coordenadas=CoordenadasZonaDTO(
                x_porcentaje=entity.coordenadas.x_porcentaje,
                y_porcentaje=entity.coordenadas.y_porcentaje,
                ancho_porcentaje=entity.coordenadas.ancho_porcentaje,
                alto_porcentaje=entity.coordenadas.alto_porcentaje,
            ),
        )

    @staticmethod
    def dto_to_zona(dto: ZonaPlantaDTO, planta_id: str) -> ZonaPlanta:
        return ZonaPlanta(
            id=dto.id or str(uuid.uuid4()),
            planta_id=planta_id,
            nombre=dto.nombre,
            coordenadas=CoordenadasZona(
                x_porcentaje=dto.coordenadas.x_porcentaje,
                y_porcentaje=dto.coordenadas.y_porcentaje,
                ancho_porcentaje=dto.coordenadas.ancho_porcentaje,
                alto_porcentaje=dto.coordenadas.alto_porcentaje,
            ),
        )

    @staticmethod
    def disp_layout_to_dto(entity: DispositivoLayout) -> DispositivoLayoutDTO:
        return DispositivoLayoutDTO(
            device_id=entity.device_id,
            zona_id=entity.zona_id,
            posicion=PosicionLayoutDTO(
                x_porcentaje=entity.posicion.x_porcentaje,
                y_porcentaje=entity.posicion.y_porcentaje,
            ),
        )

    @staticmethod
    def dto_to_disp_layout(dto: DispositivoLayoutDTO, planta_id: str) -> DispositivoLayout:
        return DispositivoLayout(
            id=str(uuid.uuid4()),
            planta_id=planta_id,
            device_id=dto.device_id,
            zona_id=dto.zona_id,
            posicion=PosicionLayout(
                x_porcentaje=dto.posicion.x_porcentaje,
                y_porcentaje=dto.posicion.y_porcentaje,
            ),
        )

    @staticmethod
    def unifilar_to_dto(entity: UnifilarPlanta) -> UnifilarPlantaDTO:
        return UnifilarPlantaDTO(
            planta_id=entity.planta_id,
            nombre_planta=entity.nombre_planta,
            nodos=[PlantaEstructuraMapper.nodo_to_dto(n) for n in entity.nodos],
        )

    @staticmethod
    def layout_to_dto(entity: LayoutPlanta) -> LayoutPlantaDTO:
        return LayoutPlantaDTO(
            planta_id=entity.planta_id,
            nombre_planta=entity.nombre_planta,
            plano_svg_url=entity.plano_svg_url,
            zonas=[PlantaEstructuraMapper.zona_to_dto(z) for z in entity.zonas],
            dispositivos=[PlantaEstructuraMapper.disp_layout_to_dto(d) for d in entity.dispositivos],
        )
