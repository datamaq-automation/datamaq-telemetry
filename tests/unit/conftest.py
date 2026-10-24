"""tests/unit/conftest.py — aislamiento del estado de clase de la ingesta entre tests.

`IngestarTelemetriaUseCase`, `ResolvedorDispositivoIngesta` y `ProcesadorAlertasIngesta`
guardan caches a nivel de clase (dispositivos resueltos, heartbeats, ventana de throttle y
el filtro de persistencia temporal de alertas) porque en producción hay un solo proceso
MQTT. En tests eso hace que el orden importe: con pytest-xdist el orden por worker cambia
y un test heredaba el estado del filtro de persistencia de otro. Se limpia antes de cada test.
"""

import pytest

from src.application.use_cases.ingestar_telemetria import IngestarTelemetriaUseCase
from src.infrastructure.fastapi.headers_historico import cache_potencia_referencia


@pytest.fixture(autouse=True)
def _aislar_estado_de_clase_ingesta():
    IngestarTelemetriaUseCase.limpiar_estado()
    cache_potencia_referencia.limpiar()
    yield
