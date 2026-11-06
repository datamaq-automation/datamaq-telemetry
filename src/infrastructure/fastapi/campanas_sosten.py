"""src/infrastructure/fastapi/campanas_sosten.py — Mantenimiento y cierre de campañas de caracterización de carga."""

import asyncio

from src.adapters.gateways.mqtt_comando_rafaga import MqttComandoRafagaGateway
from src.application.use_cases.caracterizar_carga import CaracterizarCargaUseCase
from src.application.use_cases.ingesta.registro_campanas import registro_campanas_activas
from src.infrastructure.fastapi.dependencies import get_mqtt_listener
from src.infrastructure.settings.logger import get_logger
from src.infrastructure.sqlalchemy.database import get_session_factory
from src.infrastructure.sqlalchemy.mysql_repositories import (
    MySQLCampanasRepository,
    MySQLCargasRepository,
    MySQLDispositivosRepository,
)

logger = get_logger("campanas_sosten")

INTERVALO_SOSTEN_CAMPANAS_S = 45.0
"""Menor que los 120 s de duración de la ráfaga, con margen para un reintento perdido."""


def sostener_campanas() -> tuple[int, int]:
    """Renueva la ráfaga de las campañas vivas y cierra las vencidas.

    Corre con su propia sesión de base y en un hilo aparte porque `CaracterizarCargaUseCase`
    es síncrono; el bucle que lo invoca vive en el event loop y no debe bloquearse.
    """
    session_factory = get_session_factory()
    db = session_factory()
    try:
        use_case = CaracterizarCargaUseCase(
            repo_campanas=MySQLCampanasRepository(db),
            repo_cargas=MySQLCargasRepository(db),
            repo_dispositivos=MySQLDispositivosRepository(db),
            registro=registro_campanas_activas,
            comando_rafaga=MqttComandoRafagaGateway(get_mqtt_listener()),
        )
        return use_case.sostener_campanas_activas()
    finally:
        db.close()


async def loop_campanas_activas() -> None:
    """Mantiene vivas las campañas de caracterización.

    Independiente de `_ws_heartbeat_loop`, que solo renueva la ráfaga mientras haya un
    navegador conectado: una campaña puede correr de madrugada sin nadie mirando, y en
    ese caso este bucle es lo único que impide que el medidor vuelva a 5 minutos en
    medio de la medición.

    También cierra las campañas vencidas, para que una olvidada no deje al medidor
    publicando en ráfaga y escribiendo muestras indefinidamente.
    """
    while True:
        try:
            await asyncio.sleep(INTERVALO_SOSTEN_CAMPANAS_S)
            renovadas, cerradas = await asyncio.to_thread(sostener_campanas)
            if renovadas or cerradas:
                logger.info("campanas_sostenidas", renovadas=renovadas, cerradas=cerradas)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("campanas_sosten_fallido", error=str(e))
