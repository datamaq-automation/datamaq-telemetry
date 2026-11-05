"""tests/unit/test_pro15_payload.py — conversión de los mensajes reales del Pro15 (captura 2026-11-03)."""

import json
from pathlib import Path

from src.domain.telemetria.servicios.harmonics_thd import parsear_thd_harmonics
from src.domain.telemetria.servicios.pro15_payload import (
    bloques_por_subtopico,
    parsear_topico_pro15,
)

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "pro15_mensajes_reales.json"
MENSAJES = json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_topico_pro15_valido_extrae_mac_y_subtopico():
    topico = parsear_topico_pro15("pro15/8C8C291C3FB4/inst/v1")
    assert topico is not None
    assert topico.mac == "8C8C291C3FB4"
    assert topico.subtopico == "inst"


def test_topico_pro15_no_confunde_subtopico_con_mac():
    # Con la forma genérica, `inst` quedaría como MAC. Aquí debe validarse la forma completa.
    assert parsear_topico_pro15("pro15/inst/v1") is None
    assert parsear_topico_pro15("pro15/8C8C291C3FB4/inst") is None


def test_topico_pro15_rechaza_subtopico_desconocido_y_mac_invalida():
    assert parsear_topico_pro15("pro15/8C8C291C3FB4/desconocido/v1") is None
    assert parsear_topico_pro15("pro15/ZZZZ/inst/v1") is None
    assert parsear_topico_pro15("pro15/test") is None
    assert parsear_topico_pro15("m/wifi/8C8C291C3FB4/inst/v1") is None


def test_inst_separa_los_dos_medidores_por_id():
    bloques = bloques_por_subtopico("inst", MENSAJES["inst"]["payload"])
    assert [b.medidor_id for b in bloques] == [0, 1]
    assert bloques[0].timestamp == "2026-11-03T12:00:00-03:00"


def test_inst_asigna_fases_por_posicion_y_conserva_valores():
    bloques = bloques_por_subtopico("inst", MENSAJES["inst"]["payload"])
    trafo1, trafo2 = bloques[0].datos["f"], bloques[1].datos["f"]
    assert [f["n"] for f in trafo1] == ["R", "S", "T"]
    assert trafo1[0]["v"] == 224.29
    assert trafo1[0]["p"] == 107234.98
    assert trafo2[0]["q"] == -78383.71  # Trafo 2 con potencia reactiva negativa, sin alterarla


def test_acc_convierte_kwh_y_kvarh_a_claves_a_r():
    bloques = bloques_por_subtopico("acc", MENSAJES["acc"]["payload"])
    assert [b.medidor_id for b in bloques] == [0, 1]
    fase_r = bloques[0].datos["f"][0]
    assert fase_r == {"n": "R", "a": 110.56, "r": 27.882}
    assert bloques[1].datos["f"][0]["r"] == -54.932


def test_energyio_convierte_total_a_claves_del_parser_de_energia():
    bloques = bloques_por_subtopico("energyio", MENSAJES["energyio"]["payload"])
    total = bloques[0].datos["total"]
    assert total["imported_active_energy_KWH"] == 351.878
    assert total["exported_active_energy_KWH"] == 5.715
    assert total["imported_reactive_energy_KVARH"] == 98.971
    assert total["exported_reactive_energy_KVARH"] == 2.15


def test_thd_pasa_por_el_parser_existente_de_harmonics():
    bloques = bloques_por_subtopico("thd", MENSAJES["thd"]["payload"])
    thd = parsear_thd_harmonics(bloques[0].datos)
    assert set(thd) == {"R", "S", "T"}
    assert thd["R"].thd_v_pct == 1.88
    assert thd["R"].thd_i_pct == 5.69


def test_subtopicos_sin_conversor_devuelven_vacio():
    assert bloques_por_subtopico("onoff", {"device_info": {}}) == []
    assert bloques_por_subtopico("status", {"wifi_sta": {}}) == []


def test_payload_malformado_no_lanza():
    assert bloques_por_subtopico("inst", {"no": "lista"}) == []
    assert bloques_por_subtopico("inst", [1, "x", None]) == []
    assert bloques_por_subtopico("inst", [{"id": True, "f": []}]) == []
    assert bloques_por_subtopico("acc", [{"id": 0, "f": [{"kWh": "x"}]}])[0].datos["f"][0] == {
        "n": "R",
        "a": None,
        "r": None,
    }
