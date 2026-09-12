"""tests/unit/test_dispositivos_area_mapping.py — Test de verificación para area_id y linea_id en DTO Dispositivo."""

from unittest.mock import MagicMock

from src.application.use_cases.gestionar_dispositivos import GestionarDispositivosUseCase
from src.domain.telemetria.entities import Dispositivo
from src.domain.telemetria.value_objects import MacAddress
from src.infrastructure.yaml.repositories.organizaciones_repository import YamlOrganizacionesRepository


def test_dispositivo_area_id_and_linea_id_mapping():
    yaml_repo = YamlOrganizacionesRepository(data_dir="data")
    mock_dev_repo = MagicMock()

    durax_dev1 = Dispositivo(
        id="51048a93-f1f3-4283-a708-24cbd39c7192",
        device_uid=MacAddress("51:04:8a:93:f1:f3"),
        nombre="SmartPlus Trifásico #1",
        planta_id="c64fd625-0037-4caa-b68a-800e8e0ee548",
    )
    durax_dev2 = Dispositivo(
        id="b5f4bcd6-b017-4796-bb3d-efcfb50dc8f0",
        device_uid=MacAddress("b5:f4:bc:d6:b0:17"),
        nombre="Powermeter-BF2C",
        planta_id="c64fd625-0037-4caa-b68a-800e8e0ee548",
    )
    mock_dev_repo.listar.return_value = [durax_dev1, durax_dev2]

    use_case = GestionarDispositivosUseCase(
        repo_dispositivos=mock_dev_repo,
        repo_organizaciones=yaml_repo,
    )

    dtos = use_case.listar_dispositivos(planta_id="c64fd625-0037-4caa-b68a-800e8e0ee548")

    assert len(dtos) == 2
    assert dtos[0].area_id == "area-durax-trafo-1"
    assert dtos[0].linea_id == "nodo-durax-trifasico-1"

    assert dtos[1].area_id == "area-durax-trafo-2"
    assert dtos[1].linea_id == "nodo-durax-trifasico-1"
