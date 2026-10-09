"""tests/unit/test_corriente_nominal_ti.py — Corriente nominal del TI por fase como dato maestro del YAML."""

from src.domain.telemetria.entities import Dispositivo, InstalacionMedidor
from src.domain.telemetria.servicios.datos_maestros_medidor import DatosMaestrosMedidorService
from src.domain.telemetria.value_objects import MacAddress


def _dev() -> Dispositivo:
    return Dispositivo(
        id="dev-1",
        device_uid=MacAddress("AA:BB:CC:DD:EE:01"),
        nombre="Medidor",
        modelo="SmartPlus",
        planta_id="planta-1",
    )


def test_instalacion_declara_corriente_nominal_ti_por_fase():
    inst = InstalacionMedidor(dispositivo_id="dev-1", corriente_nominal_ti_a={"R": 100.0, "S": 100.0, "T": 150.0})
    res = DatosMaestrosMedidorService.aplicar_instalacion(_dev(), inst)
    assert res.corriente_nominal_ti_a == {"R": 100.0, "S": 100.0, "T": 150.0}


def test_sin_corriente_nominal_declarada_el_dispositivo_queda_none():
    res = DatosMaestrosMedidorService.aplicar_instalacion(_dev(), InstalacionMedidor(dispositivo_id="dev-1"))
    assert res.corriente_nominal_ti_a is None


def test_corriente_nominal_declarada_queda_gobernada_por_yaml():
    inst = InstalacionMedidor(dispositivo_id="dev-1", corriente_nominal_ti_a={"R": 100.0})
    gobernados = DatosMaestrosMedidorService.campos_gobernados_por_yaml("dev-1", inst, [])
    assert "corriente_nominal_ti_a" in gobernados


def test_corriente_nominal_no_declarada_no_es_gobernada():
    inst = InstalacionMedidor(dispositivo_id="dev-1")
    gobernados = DatosMaestrosMedidorService.campos_gobernados_por_yaml("dev-1", inst, [])
    assert "corriente_nominal_ti_a" not in gobernados
