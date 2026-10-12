"""src/infrastructure/fastapi/vigilancia_conectividad.py — Marca OFFLINE los dispositivos que dejaron de publicar (#19).

`MonitorearSaludDispositivosUseCase` existía desde 2026-09-12 pero nada lo invocaba: ningún medidor pasaba nunca a
OFFLINE (Durax y Hogar seguían ONLINE horas después de su último dato). Este bucle lo corre cada 60 s dentro del
lifespan de la API.

Supone un solo proceso, como el listener MQTT y `_loop_campanas_activas`: la unit de systemd arranca uvicorn con
`--workers 1`. Con más workers el bucle correría una vez por worker; marcar OFFLINE es idempotente, pero si la alerta
está habilitada podría abrirse por duplicado. La vuelta a ONLINE la hace la ingesta al recibir el próximo mensaje
(`ResolvedorDispositivoIngesta`).
"""

import asyncio

from src.application.use_cases.monitorear_salud_dispositivos import MonitorearSaludDispositivosUseCase
from src.domain.telemetria.value_objects import ReglaAlertaConectividad
from src.infrastructure.settings.config import Settings, get_settings
from src.infrastructure.settings.logger import get_logger
from src.infrastructure.sqlalchemy.database import get_session_factory
from src.infrastructure.sqlalchemy.mysql_repositories import MySQLDispositivosRepository, MySQLTelemetriaRepository

logger = get_logger("vigilancia_conectividad")

INTERVALO_VIGILANCIA_S = 60.0


def vigilar_conectividad_una_vez(settings: Settings) -> int:
    """Corre el monitor una vez con su propia sesión. Devuelve cuántas alertas abrió (0 con la alerta apagada)."""
    db = get_session_factory()()
    try:
        monitor = MonitorearSaludDispositivosUseCase(
            repo_dispositivos=MySQLDispositivosRepository(db),
            repo_telemetria=MySQLTelemetriaRepository(db),
            logger=logger,
            regla=ReglaAlertaConectividad(timeout_segundos=settings.DISPOSITIVO_OFFLINE_TIMEOUT_S),
            generar_alerta=settings.DISPOSITIVO_OFFLINE_ALERTA_HABILITADA,
        )
        return len(monitor.ejecutar())
    finally:
        db.close()


async def loop_vigilancia_conectividad() -> None:
    while True:
        try:
            await asyncio.sleep(INTERVALO_VIGILANCIA_S)
            await asyncio.to_thread(vigilar_conectividad_una_vez, get_settings())
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("vigilancia_conectividad_fallida", error=str(e))
