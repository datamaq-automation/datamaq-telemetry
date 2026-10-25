"""MQTT_HABILITADO (#api-dev, D2): con false el listener no se crea, registra ni conecta."""

from unittest.mock import MagicMock, patch

from src.infrastructure.settings.config import Settings

MODULO = "src.infrastructure.fastapi.server"


def test_mqtt_habilitado_por_defecto_es_true() -> None:
    assert Settings().MQTT_HABILITADO is True


def test_mqtt_deshabilitado_no_llama_a_start() -> None:
    with (
        patch(f"{MODULO}.MQTTListener") as listener_cls,
        patch(f"{MODULO}.registrar_mqtt_listener") as registrar,
    ):
        from src.infrastructure.fastapi.server import _iniciar_mqtt_si_habilitado

        resultado = _iniciar_mqtt_si_habilitado(False, MagicMock())

    assert resultado is None
    listener_cls.assert_not_called()
    registrar.assert_not_called()


def test_mqtt_habilitado_crea_registra_y_arranca_el_listener() -> None:
    broadcaster = MagicMock()
    with (
        patch(f"{MODULO}.MQTTListener") as listener_cls,
        patch(f"{MODULO}.registrar_mqtt_listener") as registrar,
    ):
        from src.infrastructure.fastapi.server import _iniciar_mqtt_si_habilitado

        resultado = _iniciar_mqtt_si_habilitado(True, broadcaster)

    listener = listener_cls.return_value
    listener_cls.assert_called_once_with(publicador_eventos=broadcaster)
    registrar.assert_called_once_with(listener)
    listener.start.assert_called_once()
    assert resultado is listener
