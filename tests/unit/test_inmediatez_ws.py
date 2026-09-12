"""tests/unit/test_inmediatez_ws.py — Pruebas de inmediatez del canal en vivo (specs/inmediatez-telemetria-en-vivo.md).

Verifica que el topic `inst` difunde el `LecturaInstantaneaDTO` normalizado y que los
subtopics distintos conservan el payload crudo.
"""

from typing import Any

from src.application.use_cases.ingestar_telemetria import IngestarTelemetriaUseCase
from src.domain.telemetria.entities import Dispositivo, LecturaInstantanea
from src.domain.telemetria.value_objects import EstadoDispositivo, MacAddress


class _RepoDisp:
    def __init__(self, dispositivo: Dispositivo | None = None):
        self.dispositivos: dict[str, Dispositivo] = {}
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
    def __init__(self):
        self.instantaneas: list[LecturaInstantanea] = []
        self.alertas: list[Any] = []

    def guardar_instantanea(self, lectura: LecturaInstantanea) -> None:
        self.instantaneas.append(lectura)

    def guardar_alerta(self, alerta: Any) -> None:
        self.alertas.append(alerta)

    def listar_alertas(
        self, dispositivo_id: str | None = None, solo_abiertas: bool = False, **kwargs: object
    ) -> list[Any]:
        q = list(self.alertas)
        if dispositivo_id:
            q = [a for a in q if a.dispositivo_id == dispositivo_id]
        if solo_abiertas:
            q = [a for a in q if not a.esta_resuelta]
        return q


class _Publicador:
    def __init__(self):
        self.eventos: list[tuple[str, dict[str, Any]]] = []

    def publicar_telemetria_en_vivo(self, topico: str, datos: dict[str, Any]) -> None:
        self.eventos.append((topico, datos))


def _dispositivo_monofasico() -> Dispositivo:
    return Dispositivo(
        id="dev-mono",
        device_uid=MacAddress("D48C49F03564"),
        nombre="Powermeter-Mono",
        tipo_instalacion="1P2W",
        fases_con_ti="R",
        estado=EstadoDispositivo.ONLINE,
    )


def _limpiar_caches() -> None:
    IngestarTelemetriaUseCase._device_cache.clear()
    IngestarTelemetriaUseCase._ultimos_heartbeats.clear()
    IngestarTelemetriaUseCase._ultimas_persistencias.clear()
    IngestarTelemetriaUseCase._filtro_persistencia.limpiar()


def test_broadcast_inst_publica_dto_normalizado_para_root_n():
    _limpiar_caches()
    repo_disp = _RepoDisp(_dispositivo_monofasico())
    repo_telem = _RepoTelem()
    pub = _Publicador()
    use_case = IngestarTelemetriaUseCase(repo_disp, repo_telem, publicador=pub)

    payload = {"t": 1788303000, "n": "R", "v": 227.7, "i": 0.9, "p": 147, "q": -51}

    use_case.ejecutar("m/wifi/D48C49F03564/inst", payload)

    eventos_inst = [d for t, d in pub.eventos if t == "m/wifi/D48C49F03564/inst"]
    assert len(eventos_inst) == 1
    dto = eventos_inst[0]

    # Es el DTO normalizado, no el payload crudo de raíz.
    assert "n" not in dto
    assert "fase_r" in dto
    assert dto["fase_r"]["voltage_V"] == 227.7
    assert dto["fase_r"]["current_A"] == 0.9
    assert dto["fase_r"]["net_active_power_W"] == 147.0
    assert dto["potencia_activa_total_W"] == 147.0
    assert "analitica" in dto


def test_broadcast_subtopic_distinto_de_inst_conserva_payload_crudo():
    _limpiar_caches()
    repo_disp = _RepoDisp()
    repo_telem = _RepoTelem()
    pub = _Publicador()
    use_case = IngestarTelemetriaUseCase(repo_disp, repo_telem, publicador=pub, permitir_auto_registro=False)

    payload = {"timestamp": 1788303000, "x": 1}

    use_case.ejecutar("m/wifi/AABBCCDDEEFF/acc", payload)

    eventos_acc = [d for t, d in pub.eventos if t == "m/wifi/AABBCCDDEEFF/acc"]
    assert len(eventos_acc) == 1
    assert eventos_acc[0] == payload
