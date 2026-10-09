"""tests/unit/test_harmonics_thd_parser.py — THDv y THDi por fase desde el topic /harmonics."""

import json
from pathlib import Path

from src.domain.telemetria.servicios.harmonics_thd import ThdFase, parsear_thd_harmonics

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "harmonics_smartplus_backup.json"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_literal_produce_tres_fases_mapeadas_a_r_s_t():
    resultado = parsear_thd_harmonics(_fixture())
    assert set(resultado) == {"R", "S", "T"}
    assert resultado["R"] == ThdFase(thd_v_pct=2.560060024, thd_i_pct=992.5195313)
    assert resultado["S"] == ThdFase(thd_v_pct=2.58822608, thd_i_pct=530.9910889)
    assert resultado["T"] == ThdFase(thd_v_pct=2.556314468, thd_i_pct=299.997406)


def test_thdi_absurdo_se_conserva_tal_cual_la_fiabilidad_la_decide_otra_capa():
    resultado = parsear_thd_harmonics(_fixture())
    assert resultado["R"].thd_i_pct == 992.5195313


def test_no_depende_del_orden_de_la_lista():
    payload = _fixture()
    payload["f"] = list(reversed(payload["f"]))
    assert parsear_thd_harmonics(payload) == parsear_thd_harmonics(_fixture())


def test_fase_faltante_no_aparece_en_el_resultado():
    payload = _fixture()
    payload["f"] = [f for f in payload["f"] if f["n"] != 1]
    resultado = parsear_thd_harmonics(payload)
    assert set(resultado) == {"R", "T"}


def test_numero_de_fase_fuera_de_rango_se_ignora():
    payload = _fixture()
    payload["f"][0]["n"] = 7
    resultado = parsear_thd_harmonics(payload)
    assert "R" not in resultado


def test_valor_no_numerico_o_no_finito_de_una_fase_se_descarta_sin_tumbar_las_demas():
    payload = _fixture()
    payload["f"][0]["THDi"] = "abc"
    payload["f"][1]["THDv"] = float("nan")
    payload["f"][2]["THDv"] = True  # bool no cuenta como número
    resultado = parsear_thd_harmonics(payload)
    assert resultado["R"] == ThdFase(thd_v_pct=2.560060024, thd_i_pct=None)
    assert resultado["S"] == ThdFase(thd_v_pct=None, thd_i_pct=530.9910889)
    assert resultado["T"] == ThdFase(thd_v_pct=None, thd_i_pct=299.997406)


def test_negativo_se_descarta():
    payload = _fixture()
    payload["f"][0]["THDv"] = -1.0
    assert parsear_thd_harmonics(payload)["R"].thd_v_pct is None


def test_payload_malformado_devuelve_vacio_y_no_lanza():
    assert parsear_thd_harmonics({}) == {}
    assert parsear_thd_harmonics({"f": "no es lista"}) == {}
    assert parsear_thd_harmonics({"f": [None, 3, {"n": 0}]}) == {}
    assert parsear_thd_harmonics(None) == {}  # type: ignore[arg-type]
