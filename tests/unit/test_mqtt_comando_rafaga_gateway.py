"""tests/unit/test_mqtt_comando_rafaga_gateway.py — Gateway de comando ráfaga sobre MQTT."""

from unittest.mock import MagicMock

from src.adapters.gateways.mqtt_comando_rafaga import MqttComandoRafagaGateway


def test_activar_rafaga_sin_emisor_devuelve_false():
    """Cuando no hay listener MQTT (None), activar_rafaga devuelve False sin excepción."""
    gateway = MqttComandoRafagaGateway(emisor=None)
    result = gateway.activar_rafaga("device-1", segundos=120)
    assert result is False


def test_activar_rafaga_con_emisor_delega_al_listener():
    """Cuando hay listener, activa la ráfaga delegando."""
    emisor_mock = MagicMock()
    emisor_mock.activar_tiempo_real_dispositivo.return_value = True

    gateway = MqttComandoRafagaGateway(emisor=emisor_mock)
    result = gateway.activar_rafaga("device-1", segundos=120)

    assert result is True
    emisor_mock.activar_tiempo_real_dispositivo.assert_called_once_with("device-1", segundos=120)


def test_activar_rafaga_con_emisor_falla_propaga_false():
    """Cuando el listener falla, devuelve False."""
    emisor_mock = MagicMock()
    emisor_mock.activar_tiempo_real_dispositivo.return_value = False

    gateway = MqttComandoRafagaGateway(emisor=emisor_mock)
    result = gateway.activar_rafaga("device-1", segundos=60)

    assert result is False
    emisor_mock.activar_tiempo_real_dispositivo.assert_called_once_with("device-1", segundos=60)
