"""src/infrastructure/paho_mqtt/volcador_consumo_mqtt.py — Vuelca a la base el consumo MQTT por hora (#93).

Corre en su propio hilo, así que la ingesta no espera a la base. Si una escritura falla, el acumulado
vuelve al acumulador para no perder mensajes.
"""

import threading
from typing import Any

from src.domain.telemetria.servicios.consumo_mqtt import AcumuladorConsumoHorario
from src.infrastructure.settings.logger import get_logger
from src.infrastructure.sqlalchemy.repositories.consumo_mqtt_repository import sumar_consumo

logger = get_logger("mqtt")

CONSUMO_INTERVALO_S = 60


class VolcadorConsumoMqtt:
    def __init__(self, acumulador: AcumuladorConsumoHorario, session_factory: Any) -> None:
        self._acumulador = acumulador
        self._session_factory = session_factory
        self._detener = threading.Event()
        self._hilo: threading.Thread | None = None

    def iniciar(self) -> None:
        self._detener.clear()
        self._hilo = threading.Thread(target=self._bucle, name="mqtt-consumo-horario", daemon=True)
        self._hilo.start()

    def detener(self) -> None:
        self._detener.set()
        if self._hilo and self._hilo.is_alive():
            self._hilo.join(timeout=2.0)
        self.volcar()

    def volcar(self) -> None:
        datos = self._acumulador.extraer()
        if not datos:
            return
        try:
            sumar_consumo(self._session_factory, datos)
        except Exception as e:
            self._acumulador.fusionar(datos)
            logger.warning("mqtt_consumo_persistencia_fallida", error=str(e))

    def _bucle(self) -> None:
        while not self._detener.wait(timeout=CONSUMO_INTERVALO_S):
            self.volcar()
