"""src/application/mappers/activo_unifilar_mapper.py — Mapper de dominio a DTOs para ActivoUnifilar."""

from src.application.dtos.activo_unifilar_dto import ActivoUnifilarDTO, CrearActivoUnifilarDTO
from src.application.dtos.planta_estructura_dto import (
    CoordenadasNodoUnifilarDTO,
    NodoUnifilarDTO,
    TipoNodoUnifilarLiteral,
)
from src.domain.telemetria.entities import ActivoUnifilar
from src.domain.telemetria.servicios.clasificador_nivel_tension import clasificar_nivel_tension
from src.domain.telemetria.value_objects import TipoActivoUnifilar

_MAPEO_TIPO_A_NODO: dict[TipoActivoUnifilar, TipoNodoUnifilarLiteral] = {
    TipoActivoUnifilar.TRANSFORMADOR: "transformador",
    TipoActivoUnifilar.TGBT: "tgbt",
    TipoActivoUnifilar.TABLERO_SECCIONAL: "seccional",
    TipoActivoUnifilar.LINEA: "seccional",
    TipoActivoUnifilar.MAQUINA: "carga",
    TipoActivoUnifilar.CARGA_VIRTUAL: "carga",
}


class ActivoUnifilarMapper:
    """Conversión bidireccional y adaptación de ActivoUnifilar hacia DTOs."""

    @staticmethod
    def to_dto(activo: ActivoUnifilar) -> ActivoUnifilarDTO:
        tipo_str = activo.tipo.value if isinstance(activo.tipo, TipoActivoUnifilar) else str(activo.tipo)
        return ActivoUnifilarDTO(
            id=activo.id,
            planta_id=activo.planta_id,
            nombre=activo.nombre,
            tipo=tipo_str,  # type: ignore[arg-type]
            tension_nominal_v=activo.tension_nominal_v,
            parent_id=activo.parent_id,
            device_id=activo.device_id,
            potencia_nominal_kw=activo.potencia_nominal_kw,
            capacidad_nominal_kva=activo.capacidad_nominal_kva,
            categoria_uso=activo.categoria_uso,
            uso_significativo=activo.uso_significativo,
            posicion_x=activo.posicion_x,
            posicion_y=activo.posicion_y,
            ancho=activo.ancho,
            alto=activo.alto,
            orden=activo.orden,
            creado_en=activo.creado_en,
            actualizado_en=activo.actualizado_en,
        )

    @staticmethod
    def to_entity(dto: CrearActivoUnifilarDTO, activo_id: str) -> ActivoUnifilar:
        return ActivoUnifilar(
            id=activo_id,
            planta_id=dto.planta_id,
            nombre=dto.nombre,
            tipo=TipoActivoUnifilar(dto.tipo),
            tension_nominal_v=dto.tension_nominal_v,
            parent_id=dto.parent_id,
            device_id=dto.device_id,
            potencia_nominal_kw=dto.potencia_nominal_kw,
            capacidad_nominal_kva=dto.capacidad_nominal_kva,
            categoria_uso=dto.categoria_uso,
            uso_significativo=dto.uso_significativo,
            posicion_x=dto.posicion_x,
            posicion_y=dto.posicion_y,
            ancho=dto.ancho,
            alto=dto.alto,
            orden=dto.orden,
        )

    @classmethod
    def to_nodo_dto(cls, activo: ActivoUnifilar) -> NodoUnifilarDTO:
        tipo_nodo: TipoNodoUnifilarLiteral = _MAPEO_TIPO_A_NODO.get(activo.tipo, "seccional")
        coordenadas = None
        if activo.posicion_x is not None and activo.posicion_y is not None:
            coordenadas = CoordenadasNodoUnifilarDTO(
                x=activo.posicion_x,
                y=activo.posicion_y,
                ancho=activo.ancho,
            )

        nivel = clasificar_nivel_tension(activo.tension_nominal_v)
        return NodoUnifilarDTO(
            id=activo.id,
            parent_id=activo.parent_id,
            nombre=activo.nombre,
            tipo=tipo_nodo,
            device_id=activo.device_id,
            es_virtual=activo.device_id is None,
            es_pasante=False,
            nombre_maquina=activo.nombre if activo.tipo == TipoActivoUnifilar.MAQUINA else None,
            tension_nominal_V=activo.tension_nominal_v,
            nivel_tension=nivel,
            capacidad_nominal_kVA=activo.capacidad_nominal_kva,
            potencia_nominal_kw=activo.potencia_nominal_kw,
            uso_significativo=activo.uso_significativo,
            categoria_uso=activo.categoria_uso,
            orden=activo.orden,
            coordenadas=coordenadas,
        )
