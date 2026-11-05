"""tests/unit/test_pro15_despacho.py — despacho Pro15, device_info, identificador de medidor."""

from unittest.mock import MagicMock

import pytest

from src.application.use_cases.ingesta.ingestar_pro15 import IngestarPro15UseCase
from src.application.use_cases.ingestar_telemetria import IngestarTelemetriaUseCase
from src.domain.telemetria.exceptions import MacAddressInvalidaError
from src.domain.telemetria.servicios.identificador_medidor import parsear_identificador_medidor
from src.domain.telemetria.servicios.pro15_payload import device_info_pro15_a_formato_ingesta
from src.domain.telemetria.value_objects import MacAddress

MAC = "8C8C291C3FB4"


def _repo_vacio() -> MagicMock:
    repo = MagicMock()
    repo.obtener_por_uid.return_value = None
    repo.guardar.side_effect = lambda disp: disp
    return repo


def test_device_info_pro15_se_mapea_al_formato_del_resolvedor():
    info = {"id": MAC, "sn": "317", "fw": "V3.2.2", "model": "Smart Pro15"}
    assert device_info_pro15_a_formato_ingesta(info) == {
        "serial_number": "317",
        "device_fw": "V3.2.2",
        "device_model": "Smart Pro15",
    }


def test_device_info_pro15_sin_datos_devuelve_none():
    assert device_info_pro15_a_formato_ingesta(None) is None
    assert device_info_pro15_a_formato_ingesta({"sn": "  "}) is None


def test_despacho_pro15_registra_el_modelo_real_no_smartplus():
    repo = _repo_vacio()
    telemetria = MagicMock()
    caso = IngestarPro15UseCase(
        repo_dispositivos=repo,
        repo_telemetria=MagicMock(),
        telemetria=telemetria,
    )
    onoff = {
        "device_info": {"sn": "317", "fw": "V3.2.2", "model": "Smart Pro15"},
        "power_on": "2026-11-03T11:56:00-03:00",
    }

    caso.ejecutar(f"pro15/{MAC}/onoff/v1", onoff)

    alta = repo.guardar.call_args.args[0]
    assert alta.modelo == "Smart Pro15"
    assert alta.numero_serie == "317"


def test_regresion_pro15_auto_registro_nunca_crea_inst_ni_v1():
    repo = _repo_vacio()
    caso = IngestarPro15UseCase(repo_dispositivos=repo, repo_telemetria=MagicMock(), telemetria=MagicMock())
    inst = [{"id": 0, "t": "2026-11-03T12:00:00-03:00", "f": [{"v": 224.29, "i": 497.57, "p": 1, "q": 1}]}]

    caso.ejecutar(f"pro15/{MAC}/inst/v1", inst)

    for llamada in repo.obtener_por_uid.call_args_list:
        assert llamada.args[0].valor == MAC
    for llamada in repo.guardar.call_args_list:
        assert llamada.args[0].device_uid.valor == MAC
        assert llamada.args[0].device_uid.valor not in ("INST", "V1")


def test_despacho_pro15_llama_una_vez_por_medidor_con_su_id():
    repo = _repo_vacio()
    telemetria = MagicMock()
    caso = IngestarPro15UseCase(repo_dispositivos=repo, repo_telemetria=MagicMock(), telemetria=telemetria)
    inst = [
        {"id": 0, "t": "2026-11-03T12:00:00-03:00", "f": [{"v": 224.29, "i": 497.57, "p": 1, "q": 1}]},
        {"id": 1, "t": "2026-11-03T12:00:00-03:00", "f": [{"v": 224.29, "i": 600.13, "p": 1, "q": -2}]},
    ]

    caso.ejecutar(f"pro15/{MAC}/inst/v1", inst)

    assert telemetria.procesar_con_dispositivo.call_count == 2
    medidores = [c.args[4].medidor_id for c in telemetria.procesar_con_dispositivo.call_args_list]
    assert medidores == [0, 1]


def test_topico_generico_con_pro15_sigue_ignorado():
    repo = _repo_vacio()
    IngestarTelemetriaUseCase(repo_dispositivos=repo, repo_telemetria=MagicMock()).ejecutar(
        f"pro15/{MAC}/inst/v1", {"f": []}
    )
    repo.guardar.assert_not_called()


@pytest.mark.parametrize(
    "texto, mac, medidor",
    [
        ("8C8C291C3FB4", "8C8C291C3FB4", 0),
        ("8C8C291C3FB4_1", "8C8C291C3FB4", 1),
        ("8c:8c:29:1c:3f:b4_1", "8C8C291C3FB4", 1),
    ],
)
def test_identificador_medidor_acepta_mac_y_medidor(texto, mac, medidor):
    ident = parsear_identificador_medidor(texto)
    assert ident.mac == MacAddress(mac)
    assert ident.medidor_id == medidor


@pytest.mark.parametrize("texto", ["8C8C291C3FB4_x", "8C8C291C3FB4_1_2", "ZZZZ_1", "8C8C291C3FB4-1"])
def test_identificador_medidor_rechaza_formas_invalidas(texto):
    with pytest.raises(MacAddressInvalidaError):
        parsear_identificador_medidor(texto)


def test_inst_antes_que_onoff_registra_smart_pro15_y_nunca_smartplus():
    repo = _repo_vacio()
    caso = IngestarPro15UseCase(repo_dispositivos=repo, repo_telemetria=MagicMock(), telemetria=MagicMock())
    inst = [{"id": 0, "t": "2026-11-03T12:00:00-03:00", "f": [{"v": 224.29, "i": 497.57, "p": 1, "q": 1}]}]

    caso.ejecutar(f"pro15/{MAC}/inst/v1", inst)

    alta = repo.guardar.call_args.args[0]
    assert alta.modelo == "Smart Pro15"
    assert alta.modelo != "SmartPlus"
