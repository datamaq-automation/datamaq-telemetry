"""src/infrastructure/fastapi/renovacion_tiempo_real.py — Renovación de `realtime_sync_mode` para los clientes en vivo.

La usan dos caminos de `server.py`: el heartbeat de WebSocket (periódico) y la conexión de un cliente nuevo.
Comparten `marca_renovacion`: si la conexión ya renovó todo el alcance, el primer tick del heartbeat no tiene que
volver a renovarlo (#15: dos `realtime_mode_auto_renovado` separados por 1,4 s al conectarse).
"""

import time
from datetime import datetime, timezone
from typing import Any

from src.adapters.gateways.mqtt_comando_rafaga import MqttComandoRafagaGateway
from src.application.use_cases.renovar_tiempo_real_medidores import RenovarTiempoRealMedidoresUseCase
from src.domain.telemetria.servicios.alcance_tiempo_real import AlcanceTiempoReal
from src.infrastructure.settings.logger import get_logger
from src.infrastructure.sqlalchemy.database import get_session_factory
from src.infrastructure.sqlalchemy.mysql_repositories import MySQLDispositivosRepository

logger = get_logger("server")

INTERVALO_RENOVACION_S = 60.0
"""Menor que los 120 s de `time_s`, con margen para el tick de 25 s del heartbeat."""


class MarcaRenovacion:
    """Momento de la última renovación de **todo** el alcance conectado.

    Solo la corre el event loop (heartbeat y conexión de WebSocket), así que no necesita lock.
    """

    def __init__(self) -> None:
        self.ultima: float = 0.0

    def vencida(self, ahora_ts: float) -> bool:
        return ahora_ts - self.ultima >= INTERVALO_RENOVACION_S

    def registrar(self, ahora_ts: float | None = None) -> None:
        self.ultima = time.time() if ahora_ts is None else ahora_ts


marca_renovacion = MarcaRenovacion()


def renovar_modo_tiempo_real_medidores(listener: Any, alcance: AlcanceTiempoReal) -> None:
    """Renueva el tiempo real solo de los medidores del alcance. Nunca lanza: un fallo queda en el log."""
    if alcance.vacio:
        return
    try:
        db = get_session_factory()()
        try:
            use_case = RenovarTiempoRealMedidoresUseCase(
                MySQLDispositivosRepository(db), MqttComandoRafagaGateway(listener)
            )
            resultado = use_case.ejecutar(alcance, datetime.now(timezone.utc))
            logger.info(
                "realtime_mode_auto_renovado",
                total_dispositivos=resultado.renovados,
                omitidos_sin_recepcion_reciente=resultado.omitidos_sin_recepcion_reciente,
                organizaciones="todas" if alcance.todas else sorted(alcance.organizaciones),
            )
        finally:
            db.close()
    except Exception as e:
        logger.warning("realtime_mode_auto_renovacion_fallida", error=str(e))
