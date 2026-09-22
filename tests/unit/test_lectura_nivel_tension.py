"""tests/unit/test_lectura_nivel_tension.py — nivel_tension y nominales en LecturaInstantaneaDTO."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.application.mappers.telemetria_mapper import TelemetriaMapper
from src.domain.telemetria.entities import Dispositivo, LecturaInstantanea, MedicionFase
from src.domain.telemetria.value_objects import MacAddress, Tension

AHORA = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


def _lectura() -> LecturaInstantanea:
    fase = MedicionFase(tension=Tension(220.0))
    return LecturaInstantanea(
        id=1,
        dispositivo_id="dev-1",
        registrado_en=AHORA,
        fase_r=fase,
        fase_s=fase,
        fase_t=fase,
    )


def _dispositivo(**kw) -> Dispositivo:
    base = dict(id="dev-1", device_uid=MacAddress("AABBCCDDEE01"), nombre="PM")
    base.update(kw)
    return Dispositivo(**base)


def test_sin_dispositivo_los_tres_campos_quedan_none():
    dto = TelemetriaMapper.instantanea_to_dto(_lectura())
    assert dto.nivel_tension is None
    assert dto.tension_nominal_V is None
    assert dto.tension_nominal_fase_V is None
    assert dto.magnitud_tension_canonica is None


def test_dispositivo_sin_tension_nominal_resuelta_queda_none():
    dto = TelemetriaMapper.instantanea_to_dto(_lectura(), dispositivo=_dispositivo(tension_nominal_v=None))
    assert dto.nivel_tension is None
    assert dto.tension_nominal_V is None
    assert dto.tension_nominal_fase_V is None
    assert dto.magnitud_tension_canonica is None


def test_dispositivo_monofasico_bt_nominal_ya_es_fase_neutro():
    dev = _dispositivo(tension_nominal_v=220.0, fases_con_ti="R")
    dto = TelemetriaMapper.instantanea_to_dto(_lectura(), dispositivo=dev)
    assert dto.nivel_tension == "BT"
    assert dto.tension_nominal_V == 220.0
    assert dto.tension_nominal_fase_V == 220.0
    assert dto.magnitud_tension_canonica == "FASE"


def test_dispositivo_trifasico_bt_deriva_nominal_fase_neutro():
    dev = _dispositivo(tension_nominal_v=380.0, fases_con_ti="R,S,T")
    dto = TelemetriaMapper.instantanea_to_dto(_lectura(), dispositivo=dev)
    assert dto.nivel_tension == "BT"
    assert dto.tension_nominal_V == 380.0
    assert round(dto.tension_nominal_fase_V or 0, 1) == 219.4
    assert dto.magnitud_tension_canonica == "FASE"


def test_dispositivo_en_nodo_mt_clasifica_mt():
    dev = _dispositivo(tension_nominal_v=13200.0, fases_con_ti="R,S,T")
    dto = TelemetriaMapper.instantanea_to_dto(_lectura(), dispositivo=dev)
    assert dto.nivel_tension == "MT"
    assert dto.tension_nominal_V == 13200.0
    assert round(dto.tension_nominal_fase_V or 0, 0) == 7621.0
    assert dto.magnitud_tension_canonica == "LINEA"


def test_dispositivo_mock_no_explota_y_queda_none():
    """Regresión: `dispositivo` es `object | None`; un mock sin `tension_nominal_v`
    real no debe intentar `float(MagicMock())`."""
    dto = TelemetriaMapper.instantanea_to_dto(_lectura(), dispositivo=MagicMock())
    assert dto.nivel_tension is None
    assert dto.tension_nominal_V is None
    assert dto.tension_nominal_fase_V is None
    assert dto.magnitud_tension_canonica is None


def test_rehidratacion_de_dict_viejo_sin_los_campos_nuevos_usa_defaults():
    """El buffer en vivo rehidrata LecturaInstantaneaDTO con `model_validate` desde
    dicts en RAM (consultar_telemetria.py); un dict de antes de este cambio no debe
    romper la validación."""
    from src.application.dtos.telemetria_dto import LecturaInstantaneaDTO

    dto_original = TelemetriaMapper.instantanea_to_dto(_lectura())
    dict_viejo = dto_original.model_dump(mode="json")
    del (
        dict_viejo["nivel_tension"],
        dict_viejo["tension_nominal_V"],
        dict_viejo["tension_nominal_fase_V"],
        dict_viejo["magnitud_tension_canonica"],
    )

    dto = LecturaInstantaneaDTO.model_validate(dict_viejo)
    assert dto.nivel_tension is None
    assert dto.tension_nominal_V is None
    assert dto.tension_nominal_fase_V is None
    assert dto.magnitud_tension_canonica is None
