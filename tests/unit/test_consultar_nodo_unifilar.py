"""tests/unit/test_consultar_nodo_unifilar.py — Telemetría agregada por nodo del unifilar."""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.application.dtos.telemetria_dto import EnergiaAgregadaDTO
from src.application.use_cases.consultar_nodo_unifilar import ConsultarNodoUnifilarUseCase
from src.domain.telemetria.entities import LecturaInstantanea, MedicionFase, NodoUnifilar, Planta
from src.domain.telemetria.exceptions import NodoUnifilarNoEncontradoError, PlantaNoEncontradaError
from src.domain.telemetria.value_objects import PotenciaActiva, TipoNodoUnifilar

PLANTA_ID = "planta-durax"
ORG_ID = "org-durax"
DEV_1 = "dev-trafo-1"
DEV_2 = "dev-trafo-2"


def _nodo(id_: str, tipo: TipoNodoUnifilar, parent_id: str | None = None, device_id: str | None = None):
    return NodoUnifilar(
        id=id_,
        planta_id=PLANTA_ID,
        nombre=id_,
        tipo=tipo,
        tension_nominal_v=380.0,
        parent_id=parent_id,
        device_id=device_id,
    )


def _lectura(dispositivo_id: str, vatios: float) -> LecturaInstantanea:
    return LecturaInstantanea(
        id=None,
        dispositivo_id=dispositivo_id,
        registrado_en=datetime(2026, 9, 12, tzinfo=timezone.utc),
        fase_r=MedicionFase(),
        fase_s=MedicionFase(),
        fase_t=MedicionFase(),
        potencia_activa_total=PotenciaActiva(vatios),
    )


@pytest.fixture
def use_case():
    repo_org = MagicMock()
    repo_org.obtener_planta_por_id.return_value = Planta(id=PLANTA_ID, organizacion_id=ORG_ID, nombre="Durax")
    repo_org.obtener_nodos_unifilar.return_value = [
        _nodo("mt", TipoNodoUnifilar.ACOMETIDA),
        _nodo("trafo-1", TipoNodoUnifilar.TRANSFORMADOR, parent_id="mt", device_id=DEV_1),
        _nodo("trafo-2", TipoNodoUnifilar.TRANSFORMADOR, parent_id="mt", device_id=DEV_2),
    ]

    repo_telemetria = MagicMock()
    repo_telemetria.obtener_ultima_instantanea.side_effect = lambda dev_id: {
        DEV_1: _lectura(DEV_1, 300_000.0),
        DEV_2: _lectura(DEV_2, 150_000.0),
    }.get(dev_id)

    consultar_telemetria = MagicMock()
    consultar_telemetria.listar_energia_agregada.side_effect = lambda dev_id, *a, **k: [
        EnergiaAgregadaDTO(periodo=date(2026, 9, 12), energia_activa_neta_kwh={DEV_1: 10.0, DEV_2: 5.0}[dev_id])
    ]
    consultar_telemetria.listar_instantaneas.return_value = []

    return ConsultarNodoUnifilarUseCase(repo_org, repo_telemetria, consultar_telemetria)


def test_nodo_virtual_suma_los_dos_trafos(use_case):
    resumen = use_case.resumen(PLANTA_ID, "mt", organizacion_id=ORG_ID)

    assert resumen.es_virtual is True
    assert resumen.dispositivos_ids == [DEV_1, DEV_2]
    assert resumen.potencia_activa_total_w == 450_000.0
    assert resumen.dispositivos_sin_dato == []
    assert resumen.energia_agregada[0].energia_activa_neta_kwh == 15.0


def test_nodo_medido_devuelve_solo_su_medidor(use_case):
    resumen = use_case.resumen(PLANTA_ID, "trafo-1", organizacion_id=ORG_ID)

    assert resumen.es_virtual is False
    assert resumen.dispositivos_ids == [DEV_1]
    assert resumen.potencia_activa_total_w == 300_000.0


def test_superadmin_sin_org_accede(use_case):
    assert use_case.resumen(PLANTA_ID, "mt", organizacion_id=None).nodo_id == "mt"


def test_planta_de_otro_tenant_es_404(use_case):
    with pytest.raises(PlantaNoEncontradaError):
        use_case.resumen(PLANTA_ID, "mt", organizacion_id="otra-org")


def test_nodo_inexistente_es_404(use_case):
    with pytest.raises(NodoUnifilarNoEncontradoError):
        use_case.resumen(PLANTA_ID, "no-existe", organizacion_id=ORG_ID)


def test_historico_consulta_los_medidores_frontera(use_case):
    puntos = use_case.historico(PLANTA_ID, "mt", organizacion_id=ORG_ID, granularidad="5m", horas=1)

    llamados = [c.args[0] for c in use_case.consultar_telemetria.listar_instantaneas.call_args_list]
    assert llamados == [DEV_1, DEV_2]
    assert puntos == []
