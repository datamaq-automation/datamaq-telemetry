"""src/application/mappers/planta_estructura_mapper.py."""

from typing import Any

from src.application.dtos.planta_estructura_dto import (
    CoordenadasNodoUnifilarDTO,
    CoordenadasZonaDTO,
    DispositivoLayoutDTO,
    InterruptorCabeceraDTO,
    LayoutPlantaDTO,
    MetadatosPlacaDTO,
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
from src.domain.telemetria.servicios.clasificador_nivel_tension import clasificar_nivel_tension
from src.domain.telemetria.value_objects import (
    CoordenadasNodoUnifilar,
    InterruptorCabecera,
    MetadatosPlaca,
    TipoNodoUnifilar,
)


def _mapear_coordenadas(coordenadas: CoordenadasNodoUnifilar | None) -> CoordenadasNodoUnifilarDTO | None:
    if coordenadas is None:
        return None
    orientacion = coordenadas.orientacion if coordenadas.orientacion in ("horizontal", "vertical") else None
    return CoordenadasNodoUnifilarDTO(
        x=coordenadas.x,
        y=coordenadas.y,
        ancho=coordenadas.ancho,
        orientacion=orientacion,  # type: ignore[arg-type]
    )


def _mapear_interruptor(interruptor: InterruptorCabecera | None) -> InterruptorCabeceraDTO | None:
    if interruptor is None:
        return None
    return InterruptorCabeceraDTO(
        tag=interruptor.tag,
        tipo=interruptor.tipo,
        in_a=interruptor.in_a,
        icu_ka=interruptor.icu_ka,
        estado=interruptor.estado,
    )


def _mapear_metadatos_placa(metadatos: MetadatosPlaca | None) -> MetadatosPlacaDTO | None:
    if metadatos is None:
        return None
    meta_dict: dict[str, Any] = {}
    if metadatos.datos_adicionales:
        meta_dict.update(metadatos.datos_adicionales)
    campos = (
        "potencia_nominal_kva",
        "relacion_tension_kv",
        "vsc_porcentaje",
        "grupo_conexion",
        "corriente_nominal_a",
        "icw_ka",
        "frecuencia_hz",
        "calibre_in_a",
        "cable_seccion",
        "longitud_estimada_m",
        "tension_nominal_v",
        "categoria_tarifaria",
        "trafo_asociado_kva",
        "corriente_barra_a",
        "proteccion_in_a",
    )
    for k in campos:
        val = getattr(metadatos, k)
        if val is not None:
            meta_dict[k] = val
    return MetadatosPlacaDTO(**meta_dict)


class PlantaEstructuraMapper:
    @staticmethod
    def nodo_to_dto(
        entity: NodoUnifilar,
        nombre_maquina: str | None = None,
        es_pasante: bool | None = None,
    ) -> NodoUnifilarDTO:
        pasante_final = entity.es_pasante if es_pasante is None else es_pasante
        return NodoUnifilarDTO(
            id=entity.id,
            parent_id=entity.parent_id,
            nombre=entity.nombre,
            tipo=TipoNodoUnifilar(entity.tipo).value,
            device_id=entity.device_id,
            es_virtual=entity.device_id is None,
            es_pasante=pasante_final,
            nombre_maquina=nombre_maquina,
            tension_nominal_V=entity.tension_nominal_v,
            nivel_tension=clasificar_nivel_tension(entity.tension_nominal_v),
            capacidad_nominal_kVA=entity.capacidad_nominal_kva,
            potencia_nominal_kw=entity.potencia_nominal_kw,
            uso_significativo=entity.uso_significativo,
            categoria_uso=entity.categoria_uso,
            variable_relevante=entity.variable_relevante,
            orden=entity.orden,
            fuente_dato=entity.fuente_dato,
            notas_metrologicas=entity.notas_metrologicas,
            coordenadas=_mapear_coordenadas(entity.coordenadas),
            metadatos_placa=_mapear_metadatos_placa(entity.metadatos_placa),
            interruptor_cabecera=_mapear_interruptor(entity.interruptor_cabecera),
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
        arbol = ArbolUnifilarService(entity.nodos)
        try:
            arbol.validar()
            topologia_valida = True
        except EstructuraUnifilarInvalidaError:
            topologia_valida = False

        nodos_dto = []
        for n in entity.nodos:
            pasante = n.es_pasante or (topologia_valida and arbol.es_nodo_pasante(n.id))
            nodos_dto.append(PlantaEstructuraMapper.nodo_to_dto(n, es_pasante=pasante))

        return UnifilarPlantaDTO(
            planta_id=entity.planta_id,
            nombre_planta=entity.nombre_planta,
            nodos=nodos_dto,
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
