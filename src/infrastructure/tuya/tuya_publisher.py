"""src/infrastructure/tuya/tuya_publisher.py."""

import json

import paho.mqtt.client as mqtt

from src.infrastructure.settings.config import get_settings
from src.infrastructure.settings.logger import get_logger

logger = get_logger("tuya_publisher")


class TuyaPublisher:
    """Publicador de comandos MQTT al dispositivo GF-SMBOX-PLUS."""

    TOPIC_CONTROL = "/control/tuya/smbox"
    DEVICE_ID = "eb9195f0784612c29cy6dd"

    def __init__(self, mqtt_client: mqtt.Client | None = None):
        """Inicializa el publicador.

        Args:
            mqtt_client: Cliente MQTT existente. Si es None, crea uno nuevo.
        """
        self.settings = get_settings()
        if mqtt_client is None:
            self.client = self._crear_cliente()
        else:
            self.client = mqtt_client

    def _crear_cliente(self) -> mqtt.Client:
        """Crea un cliente MQTT configurado."""
        from paho.mqtt.enums import CallbackAPIVersion

        client = mqtt.Client(
            CallbackAPIVersion.VERSION2,
            client_id=f"{self.settings.MQTT_CLIENT_ID}_tuya_publisher",
        )
        if self.settings.MQTT_USERNAME and self.settings.MQTT_PASSWORD:
            client.username_pw_set(self.settings.MQTT_USERNAME, self.settings.MQTT_PASSWORD)

        if self.settings.MQTT_TLS_ENABLED:
            if self.settings.MQTT_TLS_CERTFILE and self.settings.MQTT_TLS_KEYFILE:
                client.tls_set(
                    ca_certs=self.settings.MQTT_TLS_CA_CERTS,
                    certfile=self.settings.MQTT_TLS_CERTFILE,
                    keyfile=self.settings.MQTT_TLS_KEYFILE,
                )
            else:
                client.tls_set(ca_certs=self.settings.MQTT_TLS_CA_CERTS)

        return client

    async def publicar_alarma_sonora(self, activar: bool) -> bool:
        """Publica comando para activar/desactivar alarma sonora.

        Args:
            activar: True para activar alarma, False para desactivar.

        Returns:
            True si la publicación fue exitosa.
        """
        comando = "alarma_sonora_on" if activar else "alarma_sonora_off"
        payload = {"comando": comando, "device_id": self.DEVICE_ID}

        try:
            if not self.client.is_connected():
                self.client.connect(
                    self.settings.MQTT_BROKER_HOST,
                    self.settings.MQTT_BROKER_PORT,
                    keepalive=60,
                )
                self.client.loop_start()

            result = self.client.publish(self.TOPIC_CONTROL, json.dumps(payload), qos=1)
            if result.rc == 0:
                logger.info(f"Comando publicado: {comando} (device={self.DEVICE_ID})")
                return True
            else:
                logger.error(f"Error al publicar comando: {result.rc}")
                return False
        except Exception as e:
            logger.error(f"Excepción al publicar comando: {e}")
            return False
