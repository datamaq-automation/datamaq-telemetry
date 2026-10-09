"""tests/unit/test_thd_i_fiable_capas.py — thd_i_fiable por fase: YAML → dispositivo → DTO."""

from datetime import datetime, timezone

from src.application.dtos.telemetria_dto import MedicionFaseDTO
from src.application.mappers.telemetria_mapper import TelemetriaMapper
from src.domain.telemetria.entities import Dispositivo, LecturaInstantanea, MedicionFase
from src.domain.telemetria.value_objects import Corriente, MacAddress
from src.infrastructure.yaml.repositories.organizaciones_repository import YamlOrganizacionesRepository

AHORA = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)


def _lectura(corriente_r: float, thd_i_r: float) -> LecturaInstantanea:
    fase_r = MedicionFase(corriente=Corriente(corriente_r), thd_i_porcentaje=thd_i_r)
    fase_sin_ti = MedicionFase(corriente=Corriente(20.0), thd_i_porcentaje=3.0)
    return LecturaInstantanea(
        id=1,
        dispositivo_id="dev-1",
        registrado_en=AHORA,
        fase_r=fase_r,
        fase_s=fase_sin_ti,
        fase_t=fase_sin_ti,
    )


def _dispositivo(corriente_nominal_ti_a: dict[str, float] | None) -> Dispositivo:
    return Dispositivo(
        id="dev-1",
        device_uid=MacAddress("AABBCCDDEE01"),
        nombre="PM",
        corriente_nominal_ti_a=corriente_nominal_ti_a,
    )


# --- DTO ---


def test_medicion_fase_dto_thd_i_fiable_por_defecto_es_none():
    assert MedicionFaseDTO().thd_i_fiable is None


# --- Mapper: con TI declarado ---


def test_fase_con_corriente_bajo_el_minimo_no_es_fiable():
    dto = TelemetriaMapper.instantanea_to_dto(
        _lectura(corriente_r=0.022, thd_i_r=992.5),
        dispositivo=_dispositivo({"R": 100.0}),
    )
    assert dto.fase_r.thd_i_fiable is False
    # El valor crudo se conserva: la app decide cómo mostrarlo, el backend solo marca.
    assert dto.fase_r.thd_i_pct == 992.5


def test_fase_con_corriente_sobre_el_minimo_es_fiable():
    dto = TelemetriaMapper.instantanea_to_dto(
        _lectura(corriente_r=60.0, thd_i_r=4.2),
        dispositivo=_dispositivo({"R": 100.0}),
    )
    assert dto.fase_r.thd_i_fiable is True


def test_fase_sin_ti_declarado_queda_none_nunca_true():
    dto = TelemetriaMapper.instantanea_to_dto(
        _lectura(corriente_r=60.0, thd_i_r=4.2),
        dispositivo=_dispositivo({"S": 100.0}),  # R no declarada
    )
    assert dto.fase_r.thd_i_fiable is None


# --- Mapper: sin TI declarado en absoluto ---


def test_sin_dispositivo_thd_i_fiable_queda_none():
    dto = TelemetriaMapper.instantanea_to_dto(_lectura(corriente_r=60.0, thd_i_r=4.2))
    assert dto.fase_r.thd_i_fiable is None
    assert dto.fase_s.thd_i_fiable is None


def test_dispositivo_sin_corriente_nominal_queda_none_en_todas_las_fases():
    dto = TelemetriaMapper.instantanea_to_dto(
        _lectura(corriente_r=60.0, thd_i_r=4.2),
        dispositivo=_dispositivo(None),
    )
    assert dto.fase_r.thd_i_fiable is None
    assert dto.fase_t.thd_i_fiable is None


# --- YAML ---


def _repo_con_medidor(tmp_path, bloque_ti: str) -> YamlOrganizacionesRepository:
    (tmp_path / "org.yml").write_text(
        f"""
organizaciones:
  - id: "org-x"
    nombre: "Org X"
    plantas:
      - id: "planta-x"
        nombre: "Planta X"
        medidores:
          - id: "meter-x"
            dispositivo_id: "11111111-2222-3333-4444-555555555555"
{bloque_ti}
""",
        encoding="utf-8",
    )
    return YamlOrganizacionesRepository(data_dir=str(tmp_path))


def test_yaml_lee_corriente_nominal_ti_por_fase(tmp_path):
    repo = _repo_con_medidor(
        tmp_path,
        "            corriente_nominal_ti_a:\n              R: 100\n              S: 100\n              T: 150",
    )
    inst = repo.obtener_instalacion_medidor("11111111-2222-3333-4444-555555555555")
    assert inst is not None
    assert inst.corriente_nominal_ti_a == {"R": 100.0, "S": 100.0, "T": 150.0}


def test_yaml_sin_corriente_nominal_ti_queda_none(tmp_path):
    repo = _repo_con_medidor(tmp_path, '            tag_ubicacion: "TGBT"')
    inst = repo.obtener_instalacion_medidor("11111111-2222-3333-4444-555555555555")
    assert inst is not None
    assert inst.corriente_nominal_ti_a is None


def test_yaml_descarta_valores_no_positivos_o_no_numericos(tmp_path):
    repo = _repo_con_medidor(
        tmp_path,
        '            corriente_nominal_ti_a:\n              R: 100\n              S: 0\n              T: "abc"',
    )
    inst = repo.obtener_instalacion_medidor("11111111-2222-3333-4444-555555555555")
    assert inst is not None
    assert inst.corriente_nominal_ti_a == {"R": 100.0}
