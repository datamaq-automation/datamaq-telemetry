"""src/application/mappers/planta_estructura_mapper.py."""

from src.application.dtos.planta_estructura_dto import (
    UMBRAL_MEDIA_TENSION_V,
    CoordenadasZonaDTO,
    DispositivoLayoutDTO,
    LayoutPlantaDTO,
    NivelTensionLiteral,
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
from src.domain.telemetria.exceptions import EstructuraUnifilarInvalidaError
from src.domain.telemetria.servicios.arbol_unifilar import ArbolUnifilarService
from src.domain.telemetria.value_objects import (
    TipoNodoUnifilar,
)


def _nivel_tension(tension_nominal_v: float) -> NivelTensionLiteral:
    return "MT" if tension_nominal_v > UMBRAL_MEDIA_TENSION_V else "BT"


class PlantaEstructuraMapper:
    @staticmethod
    def nodo_to_dto(entity: NodoUnifilar, nombre_maquina: str | None = None) -> NodoUnifilarDTO:
        return NodoUnifilarDTO(
            id=entity.id,
            parent_id=entity.parent_id,
            nombre=entity.nombre,
            tipo=TipoNodoUnifilar(entity.tipo).value,
            device_id=entity.device_id,
            es_virtual=entity.device_id is None,
            nombre_maquina=nombre_maquina,
            tension_nominal_V=entity.tension_nominal_v,
            nivel_tension=_nivel_tension(entity.tension_nominal_v),
            capacidad_nominal_kVA=entity.capacidad_nominal_kva,
            potencia_nominal_kw=entity.potencia_nominal_kw,
            uso_significativo=entity.uso_significativo,
            categoria_uso=entity.categoria_uso,
            variable_relevante=entity.variable_relevante,
            orden=entity.orden,
            fuente_dato=entity.fuente_dato,
            notas_metrologicas=entity.notas_metrologicas,
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
    def unifilar_to_dto(entity: UnifilarPlanta) -> UnifilarPlantaDTO:
        try:
            ArbolUnifilarService(entity.nodos).validar()
            topologia_valida = True
        except EstructuraUnifilarInvalidaError:
            topologia_valida = False
        return UnifilarPlantaDTO(
            planta_id=entity.planta_id,
            nombre_planta=entity.nombre_planta,
            nodos=[PlantaEstructuraMapper.nodo_to_dto(n) for n in entity.nodos],
            topologia_valida=topologia_valida,
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
