"""tests/unit/test_mqtt_eco_comando_propio.py — El backend no debe confundir el eco de sus propios comandos MQTT (conf/com) con
actividad genuina del dispositivo. Ver plan de aislamiento cross-tenant / falso ONLINE.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from src.application.use_cases.ingestar_telemetria import IngestarTelemetriaUseCase
from src.domain.telemetria.entities import Dispositivo
from src.domain.telemetria.value_objects import EstadoDispositivo, MacAddress
from src.infrastructure.paho_mqtt.mqtt_listener import MQTTListener


class _RepoDisp:
    def __init__(self, dispositivo: Dispositivo | None = None):
        self.dispositivos: dict[str, Dispositivo] = {}
        self.llamadas_guardar: list[str] = []
        if dispositivo is not None:
            self.dispositivos[dispositivo.id] = dispositivo

    def obtener_por_uid(self, uid: MacAddress) -> Dispositivo | None:
        for d in self.dispositivos.values():
            if d.device_uid.valor == uid.valor:
                return d
        return None

    def obtener_por_id(self, dispositivo_id: str) -> Dispositivo | None:
        return self.dispositivos.get(dispositivo_id)

    def guardar(self, dispositivo: Dispositivo) -> Dispositivo:
        self.llamadas_guardar.append(dispositivo.id)
        self.dispositivos[dispositivo.id] = dispositivo
        return dispositivo

    def actualizar_heartbeat(
        self, dispositivo_id, estado, visto_por_ultima_vez, numero_serie=None, version_fw=None, version_hw=None
    ) -> None:
        d = self.dispositivos.get(dispositivo_id)
        if d:
            d.estado = estado
            d.visto_por_ultima_vez = visto_por_ultima_vez

    def listar(self, planta_id: str | None = None) -> list[Dispositivo]:
        return list(self.dispositivos.values())

    def contar_por_organizacion(self, organizacion_id: str) -> int:
        return len(self.dispositivos)


class _RepoTelem:
    def guardar_instantanea(self, lectura) -> None:
        pass

    def guardar_alerta(self, alerta) -> None:
        pass

    def listar_alertas(self, **kwargs) -> list:
        return []


class _Publicador:
    def __init__(self):
        self.eventos: list[tuple[str, dict[str, Any]]] = []

    def publicar_telemetria_en_vivo(self, topico: str, datos: dict[str, Any]) -> None:
        self.eventos.append((topico, datos))


def _dispositivo() -> Dispositivo:
    return Dispositivo(
        id="dev-1",
        device_uid=MacAddress("AABBCCDDEEFF"),
        nombre="Powermeter-EEFF",
        estado=EstadoDispositivo.ONLINE,
    )


def _limpiar_caches() -> None:
    IngestarTelemetriaUseCase.limpiar_estado()


def test_conf_com_no_marca_online_ni_retransmite():
    _limpiar_caches()
    repo_disp = _RepoDisp(_dispositivo())
    pub = _Publicador()
    use_case = IngestarTelemetriaUseCase(repo_disp, _RepoTelem(), publicador=pub)

    use_case.ejecutar("m/wifi/AABBCCDDEEFF/conf/com", {"correlatorid": 1, "set": "realtime_sync_mode"})

    assert repo_disp.llamadas_guardar == []
    assert pub.eventos == []


def test_conf_rta_si_marca_online_y_retransmite():
    _limpiar_caches()
    repo_disp = _RepoDisp(_dispositivo())
    pub = _Publicador()
    use_case = IngestarTelemetriaUseCase(repo_disp, _RepoTelem(), publicador=pub)

    use_case.ejecutar("m/wifi/AABBCCDDEEFF/conf/rta", {"correlatorid": 1, "status": "ok"})

    assert repo_disp.llamadas_guardar == ["dev-1"]
    eventos_conf = [t for t, _ in pub.eventos if t == "m/wifi/AABBCCDDEEFF/conf/rta"]
    assert len(eventos_conf) == 1


def test_topico_conf_sin_sufijo_no_rompe():
    _limpiar_caches()
    repo_disp = _RepoDisp(_dispositivo())
    pub = _Publicador()
    use_case = IngestarTelemetriaUseCase(repo_disp, _RepoTelem(), publicador=pub)

    # Sin 5ta parte (ni "com" ni "rta"): no debe lanzar excepción.
    use_case.ejecutar("m/wifi/AABBCCDDEEFF/conf", {})


def _listener_falso() -> MQTTListener:
    listener = MQTTListener.__new__(MQTTListener)
    listener.settings = MagicMock(MQTT_MAX_PAYLOAD_BYTES=65536)
    listener._dedup = MagicMock()
    listener._dedup.es_duplicado.return_value = False
    listener._executor = MagicMock()
    return listener


def test_listener_descarta_el_eco_conf_com_antes_de_la_ingesta():
    listener = _listener_falso()
    msg = MagicMock(topic="m/wifi/AABBCCDDEEFF/conf/com", payload=b'{"set": "realtime_sync_mode"}')
    with patch("src.infrastructure.paho_mqtt.mqtt_listener.logger") as logger:
        listener._on_message(None, None, msg)
    listener._executor.submit.assert_not_called()
    logger.info.assert_not_called()
    logger.debug.assert_called_once_with("mqtt_eco_comando_propio_descartado", topico=msg.topic)


def test_listener_procesa_conf_rta_del_medidor():
    listener = _listener_falso()
    msg = MagicMock(topic="m/wifi/AABBCCDDEEFF/conf/rta", payload=b'{"status": "ok"}')
    with patch("src.infrastructure.paho_mqtt.mqtt_listener.logger"):
        listener._on_message(None, None, msg)
    listener._executor.submit.assert_called_once()
