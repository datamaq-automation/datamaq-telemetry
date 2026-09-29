"""src/infrastructure/tuya/tuya_listener.py."""

import json

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from src.infrastructure.settings.config import get_settings
from src.infrastructure.settings.logger import get_logger

logger = get_logger("tuya_listener")


class TuyaListener:
    """Escucha eventos del dispositivo GF-SMBOX-PLUS."""

    TOPIC_EVENTS = "/device/tuya/smbox/events"

    def __init__(self, callback_evento=None):
        """Inicializa el listener.

        Args:
            callback_evento: Función a llamar cuando se recibe un evento.
                            Firma: callback_evento(evento: dict) -> None
        """
        self.settings = get_settings()
        self.callback_evento = callback_evento
        self.client = mqtt.Client(
            CallbackAPIVersion.VERSION2,
            client_id=f"{self.settings.MQTT_CLIENT_ID}_tuya_listener",
        )
        if self.settings.MQTT_USERNAME and self.settings.MQTT_PASSWORD:
            self.client.username_pw_set(self.settings.MQTT_USERNAME, self.settings.MQTT_PASSWORD)

        if self.settings.MQTT_TLS_ENABLED:
            if self.settings.MQTT_TLS_CERTFILE and self.settings.MQTT_TLS_KEYFILE:
                self.client.tls_set(
                    ca_certs=self.settings.MQTT_TLS_CA_CERTS,
                    certfile=self.settings.MQTT_TLS_CERTFILE,
                    keyfile=self.settings.MQTT_TLS_KEYFILE,
                )
            else:
                self.client.tls_set(ca_certs=self.settings.MQTT_TLS_CA_CERTS)

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self._esta_conectado = False

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        """Callback de conexión."""
        if reason_code == 0:
            self._esta_conectado = True
            logger.info("TuyaListener conectado al broker MQTT")
            client.subscribe(self.TOPIC_EVENTS, qos=1)
        else:
            logger.error(f"Error de conexión: {reason_code}")

    def _on_message(self, client, userdata, msg):
        """Callback de mensaje MQTT."""
        try:
            evento = json.loads(msg.payload.decode())
            logger.info(f"Evento Tuya recibido: {evento}")
            if self.callback_evento:
                self.callback_evento(evento)
        except json.JSONDecodeError:
            logger.error(f"Payload inválido: {msg.payload}")

    async def escuchar_eventos(self):
        """Inicia la escucha de eventos (bloqueante)."""
        try:
            self.client.connect(
                self.settings.MQTT_BROKER_HOST,
                self.settings.MQTT_BROKER_PORT,
                keepalive=60,
            )
            logger.info("TuyaListener iniciado")
            self.client.loop_forever()
        except Exception as e:
            logger.error(f"Error al iniciar listener: {e}")
