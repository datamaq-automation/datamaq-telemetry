"""src/adapters/gateways/mqtt_comando_rafaga.py — Adaptador del puerto de ráfaga sobre el listener MQTT."""

from typing import Protocol

from src.domain.maquinas.ports import ComandoRafagaPort


class EmisorRafaga(Protocol):
    """Lo mínimo que el gateway necesita del listener MQTT.

    Se tipa como `Protocol` y no importando `MQTTListener` porque `adapters/` no puede
    depender de `infrastructure/` (regla de dependencia, verificada por
    `scripts/verify_architecture.py`). El listener la cumple por forma, sin saberlo.
    """

    def activar_tiempo_real_dispositivo(self, device_uid: str, segundos: int = 120) -> bool: ...


class MqttComandoRafagaGateway(ComandoRafagaPort):
    """Traduce "quiero alta resolución" a `realtime_sync_mode` sobre MQTT.

    Tolera no tener listener: si el broker está caído o el proceso arrancó sin él, la
    campaña igual se abre y captura lo que llegue. Vale la pena porque cuando hay un
    cliente WebSocket conectado el medidor ya está en ráfaga por otro camino, así que
    una campaña puede salir bien incluso sin que este comando prospere.
    """

    def __init__(self, emisor: EmisorRafaga | None):
        self.emisor = emisor

    def activar_rafaga(self, device_uid: str, segundos: int) -> bool:
        if self.emisor is None:
            return False
        return self.emisor.activar_tiempo_real_dispositivo(device_uid, segundos=segundos)
