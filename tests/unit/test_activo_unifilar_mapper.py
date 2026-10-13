"""tests/unit/test_activo_unifilar_mapper.py — Tests para ActivoUnifilarMapper."""

from src.application.dtos.activo_unifilar_dto import CrearActivoUnifilarDTO
from src.application.mappers.activo_unifilar_mapper import ActivoUnifilarMapper
from src.domain.telemetria.entities import ActivoUnifilar
from src.domain.telemetria.value_objects import TipoActivoUnifilar


def test_mapper_to_dto_y_to_entity():
    dto_crear = CrearActivoUnifilarDTO(
        planta_id="planta-1",
        nombre="Línea Soldadura",
        tipo="LINEA",
        tension_nominal_v=380.0,
        parent_id="tgbt-1",
        potencia_nominal_kw=50.0,
        capacidad_nominal_kva=63.0,
        categoria_uso="Fuerza Motriz",
        uso_significativo=True,
        posicion_x=15.0,
        posicion_y=30.0,
        ancho=40.0,
        alto=20.0,
        orden=3,
    )

    entidad = ActivoUnifilarMapper.to_entity(dto_crear, "act-soldadura")
    assert entidad.id == "act-soldadura"
    assert entidad.planta_id == "planta-1"
    assert entidad.nombre == "Línea Soldadura"
    assert entidad.tipo == TipoActivoUnifilar.LINEA
    assert entidad.tension_nominal_v == 380.0
    assert entidad.potencia_nominal_kw == 50.0

    dto_recuperado = ActivoUnifilarMapper.to_dto(entidad)
    assert dto_recuperado.id == "act-soldadura"
    assert dto_recuperado.tipo == "LINEA"
    assert dto_recuperado.posicion_x == 15.0
    assert dto_recuperado.posicion_y == 30.0
    assert dto_recuperado.orden == 3


def test_mapper_to_nodo_dto_tension_y_tipo():
    # 1. Transformador MT
    trafo = ActivoUnifilar(
        id="trafo-mt",
        planta_id="planta-1",
        nombre="Trafo Principal",
        tipo=TipoActivoUnifilar.TRANSFORMADOR,
        tension_nominal_v=13200.0,
    )
    nodo_trafo = ActivoUnifilarMapper.to_nodo_dto(trafo)
    assert nodo_trafo.id == "trafo-mt"
    assert nodo_trafo.tipo == "transformador"
    assert nodo_trafo.nivel_tension == "MT"
    assert nodo_trafo.es_virtual is True

    # 2. Máquina BT con dispositivo vinculado
    maquina = ActivoUnifilar(
        id="maq-torno",
        planta_id="planta-1",
        nombre="Torno CNC",
        tipo=TipoActivoUnifilar.MAQUINA,
        tension_nominal_v=380.0,
        device_id="dev-123",
        posicion_x=50.0,
        posicion_y=60.0,
    )
    nodo_maq = ActivoUnifilarMapper.to_nodo_dto(maquina)
    assert nodo_maq.id == "maq-torno"
    assert nodo_maq.tipo == "carga"
    assert nodo_maq.nivel_tension == "BT"
    assert nodo_maq.es_virtual is False
    assert nodo_maq.nombre_maquina == "Torno CNC"
    assert nodo_maq.coordenadas is not None
    assert nodo_maq.coordenadas.x == 50.0
    assert nodo_maq.coordenadas.y == 60.0
