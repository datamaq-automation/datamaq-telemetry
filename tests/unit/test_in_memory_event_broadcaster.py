"""tests/unit/test_in_memory_event_broadcaster.py — Issue datamaq#149: el broadcaster no traga errores de listeners.

Un listener que lanza no corta a los demás, y su fallo queda en el log de error con el tópico y el nombre del listener.
Suscribir dos veces el mismo listener lo deja una sola vez. Desuscribir sigue siendo idempotente.
"""

from unittest.mock import MagicMock

from src.adapters.gateways.in_memory_event_broadcaster import InMemoryEventBroadcaster
from src.domain.telemetria.ports import LoggerPort


def _listener_malo(topico, datos):
    raise RuntimeError("fallo del listener")


def test_listener_que_lanza_no_corta_a_los_demas():
    logger = MagicMock(spec=LoggerPort)
    broadcaster = InMemoryEventBroadcaster(logger=logger)
    recibidos: list[str] = []
    broadcaster.suscribir(_listener_malo)
    broadcaster.suscribir(lambda topico, datos: recibidos.append(topico))

    broadcaster.publicar_telemetria_en_vivo("m/wifi/AA/inst", {"x": 1})

    assert recibidos == ["m/wifi/AA/inst"]


def test_fallo_de_listener_queda_registrado_con_topico_y_nombre():
    logger = MagicMock(spec=LoggerPort)
    broadcaster = InMemoryEventBroadcaster(logger=logger)
    broadcaster.suscribir(_listener_malo)

    broadcaster.publicar_telemetria_en_vivo("m/wifi/AA/inst", {"x": 1})

    logger.error.assert_called_once()
    evento = logger.error.call_args.args[0]
    kwargs = logger.error.call_args.kwargs
    assert evento == "listener_broadcast_fallo"
    assert kwargs["topico"] == "m/wifi/AA/inst"
    assert "_listener_malo" in kwargs["listener"]
    assert "fallo del listener" in kwargs["error"]


def test_suscribir_el_mismo_listener_dos_veces_lo_deja_una_vez():
    broadcaster = InMemoryEventBroadcaster(logger=MagicMock(spec=LoggerPort))
    llamadas: list[str] = []

    def listener(topico, datos):
        llamadas.append(topico)

    broadcaster.suscribir(listener)
    broadcaster.suscribir(listener)
    broadcaster.publicar_telemetria_en_vivo("t", {})

    assert llamadas == ["t"]


def test_desuscribir_es_idempotente():
    broadcaster = InMemoryEventBroadcaster(logger=MagicMock(spec=LoggerPort))

    def listener(topico, datos):
        pass

    broadcaster.suscribir(listener)
    broadcaster.desuscribir(listener)
    broadcaster.desuscribir(listener)
    broadcaster.publicar_telemetria_en_vivo("t", {})


def test_listeners_sanos_siguen_recibiendo_sin_errores_registrados():
    logger = MagicMock(spec=LoggerPort)
    broadcaster = InMemoryEventBroadcaster(logger=logger)
    recibidos: list[tuple[str, dict]] = []
    broadcaster.suscribir(lambda topico, datos: recibidos.append((topico, datos)))

    broadcaster.publicar_telemetria_en_vivo("t", {"v": 2})

    assert recibidos == [("t", {"v": 2})]
    logger.error.assert_not_called()


def test_sin_logger_inyectado_sigue_funcionando():
    broadcaster = InMemoryEventBroadcaster()
    recibidos: list[str] = []
    broadcaster.suscribir(_listener_malo)
    broadcaster.suscribir(lambda topico, datos: recibidos.append(topico))

    broadcaster.publicar_telemetria_en_vivo("t", {})

    assert recibidos == ["t"]
