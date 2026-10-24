"""tests/unit/conftest.py — aislamiento del estado de clase de la ingesta entre tests.

`IngestarTelemetriaUseCase`, `ResolvedorDispositivoIngesta` y `ProcesadorAlertasIngesta`
guardan caches a nivel de clase (dispositivos resueltos, heartbeats, ventana de throttle y
el filtro de persistencia temporal de alertas) porque en producción hay un solo proceso
MQTT. En tests eso hace que el orden importe: con pytest-xdist el orden por worker cambia
y un test heredaba el estado del filtro de persistencia de otro. Se limpia antes de cada test.
"""

import pytest

from src.application.use_cases.ingestar_telemetria import IngestarTelemetriaUseCase
from src.infrastructure.fastapi.dependencies import get_rate_limiter, get_token_revocation_service
from src.infrastructure.fastapi.headers_historico import cache_potencia_referencia


@pytest.fixture(autouse=True)
def _aislar_estado_de_clase_ingesta():
    IngestarTelemetriaUseCase.limpiar_estado()
    cache_potencia_referencia.limpiar()
    yield


@pytest.fixture(autouse=True)
def _aislar_singletons_con_estado_de_dependencias():
    """Rate limiter y revocación de tokens guardan estado en memoria y viven en una caché de función.

    Sin este reset, un test que registra intentos fallidos o revoca un token afecta a los siguientes.
    """
    get_rate_limiter.cache_clear()
    get_token_revocation_service.cache_clear()
    yield
    get_rate_limiter.cache_clear()
    get_token_revocation_service.cache_clear()
