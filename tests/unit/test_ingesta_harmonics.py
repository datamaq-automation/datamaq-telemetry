"""tests/unit/test_ingesta_harmonics.py — Despacho de /harmonics y ventana de unión con /inst.

La ventana es granularidad + 60 s a propósito: /inst solo persiste una fila por granularidad_segundos,
así que el THD queda en la fila persistida más reciente. Por eso thd_i_fiable se calcula con la corriente
de esa fila, que puede diferir hasta ~5 min del instante en que se midió el THD. Si la carga cambió en ese
lapso, la fiabilidad puede quedar mal clasificada. Es una salvedad conocida y aceptada, no un bug.
"""

import json
from pathlib import Path
from typing import Any

from src.application.use_cases.ingestar_harmonics_thd import (
    MARGEN_VENTANA_THD_S,
    IngestarHarmonicsThdUseCase,
    ventana_thd_s,
)
from src.application.use_cases.ingestar_telemetria import IngestarTelemetriaUseCase
from src.domain.telemetria.entities import Dispositivo
from src.domain.telemetria.value_objects import EstadoDispositivo, MacAddress

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "harmonics_smartplus_backup.json"
TOPICO = "m/wifi/AABBCCDDEEFF/harmonics"


def _payload_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class _RepoTelem:
    def __init__(self, resultado_actualizar: bool = True) -> None:
        self.resultado_actualizar = resultado_actualizar
        self.instantaneas: list[object] = []
        self.thd_llamadas: list[tuple[str, object, int, dict[str, Any]]] = []

    def guardar_instantanea(self, lectura: object) -> None:
        self.instantaneas.append(lectura)

    def guardar_alerta(self, alerta: object) -> None:
        pass

    def listar_alertas(self, **kwargs: Any) -> list[object]:
        return []

    def actualizar_thd_instantanea(self, dispositivo_id: str, momento: object, ventana_s: int, thd: Any) -> bool:
        self.thd_llamadas.append((dispositivo_id, momento, ventana_s, thd))
        return self.resultado_actualizar


class _RepoDisp:
    def __init__(self) -> None:
        self.dispositivos = {
            "dev-1": Dispositivo(
                id="dev-1",
                device_uid=MacAddress("AABBCCDDEEFF"),
                nombre="Powermeter-EEFF",
                estado=EstadoDispositivo.ONLINE,
            )
        }

    def obtener_por_uid(self, uid: MacAddress) -> Dispositivo | None:
        return next((d for d in self.dispositivos.values() if d.device_uid.valor == uid.valor), None)

    def obtener_por_id(self, dispositivo_id: str) -> Dispositivo | None:
        return self.dispositivos.get(dispositivo_id)

    def guardar(self, dispositivo: Dispositivo) -> Dispositivo:
        self.dispositivos[dispositivo.id] = dispositivo
        return dispositivo

    def actualizar_heartbeat(self, *args: Any, **kwargs: Any) -> None:
        pass

    def listar(self, planta_id: str | None = None) -> list[Dispositivo]:
        return list(self.dispositivos.values())

    def contar_por_organizacion(self, organizacion_id: str) -> int:
        return len(self.dispositivos)


class _Publicador:
    def __init__(self) -> None:
        self.eventos: list[str] = []

    def publicar_telemetria_en_vivo(self, topico: str, datos: dict[str, Any]) -> None:
        self.eventos.append(topico)


def _limpiar_caches() -> None:
    IngestarTelemetriaUseCase._device_cache.clear()
    IngestarTelemetriaUseCase._ultimos_heartbeats.clear()
    IngestarTelemetriaUseCase._ultimas_persistencias.clear()
    IngestarTelemetriaUseCase._filtro_persistencia.limpiar()


# --- Ventana ---


def test_ventana_es_granularidad_mas_margen_de_60_segundos():
    assert MARGEN_VENTANA_THD_S == 60
    assert ventana_thd_s(300) == 360
    assert ventana_thd_s(0) == 60


# --- Caso de uso ---


def test_caso_de_uso_envia_el_thd_parseado_a_la_ventana_correcta():
    repo = _RepoTelem()
    IngestarHarmonicsThdUseCase(repo, granularidad_segundos=300).ejecutar("dev-1", _payload_fixture(), "MOMENTO")
    assert len(repo.thd_llamadas) == 1
    dispositivo_id, momento, ventana, thd = repo.thd_llamadas[0]
    assert (dispositivo_id, momento, ventana) == ("dev-1", "MOMENTO", 360)
    assert set(thd) == {"R", "S", "T"}


def test_payload_sin_thd_valido_no_llama_al_repositorio():
    repo = _RepoTelem()
    resultado = IngestarHarmonicsThdUseCase(repo, granularidad_segundos=300).ejecutar("dev-1", {"f": "roto"}, "M")
    assert resultado is False
    assert repo.thd_llamadas == []


def test_sin_fila_en_la_ventana_devuelve_false_sin_lanzar():
    repo = _RepoTelem(resultado_actualizar=False)
    resultado = IngestarHarmonicsThdUseCase(repo, granularidad_segundos=300).ejecutar("dev-1", _payload_fixture(), "M")
    assert resultado is False


# --- Despacho desde IngestarTelemetriaUseCase ---


def test_topico_harmonics_actualiza_thd_y_no_crea_instantanea():
    _limpiar_caches()
    repo_telem = _RepoTelem()
    IngestarTelemetriaUseCase(_RepoDisp(), repo_telem, granularidad_segundos=300).ejecutar(TOPICO, _payload_fixture())
    assert len(repo_telem.thd_llamadas) == 1
    assert repo_telem.thd_llamadas[0][0] == "dev-1"
    assert repo_telem.thd_llamadas[0][2] == 360
    assert repo_telem.instantaneas == []


def test_topico_harmonics_no_se_retransmite_en_vivo():
    _limpiar_caches()
    pub = _Publicador()
    IngestarTelemetriaUseCase(_RepoDisp(), _RepoTelem(), publicador=pub).ejecutar(TOPICO, _payload_fixture())
    assert pub.eventos == []


def test_payload_harmonics_malformado_no_tumba_el_listener():
    _limpiar_caches()
    repo_telem = _RepoTelem()
    use_case = IngestarTelemetriaUseCase(_RepoDisp(), repo_telem)
    use_case.ejecutar(TOPICO, {"f": [None, 3, {"n": "x"}]})
    use_case.ejecutar(TOPICO, {})
    assert repo_telem.thd_llamadas == []


def test_fase_faltante_en_harmonics_se_guarda_solo_la_presente():
    _limpiar_caches()
    repo_telem = _RepoTelem()
    payload = _payload_fixture()
    payload["f"] = [f for f in payload["f"] if f["n"] != 0]
    IngestarTelemetriaUseCase(_RepoDisp(), repo_telem).ejecutar(TOPICO, payload)
    thd = repo_telem.thd_llamadas[0][3]
    assert set(thd) == {"S", "T"}


def test_thdi_absurdo_se_persiste_tal_cual():
    _limpiar_caches()
    repo_telem = _RepoTelem()
    IngestarTelemetriaUseCase(_RepoDisp(), repo_telem).ejecutar(TOPICO, _payload_fixture())
    assert repo_telem.thd_llamadas[0][3]["R"].thd_i_pct == 992.5195313
