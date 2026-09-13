"""tests/unit/test_energia_fuente_y_prioridad.py — WP2: serie única de energía (D1, D3).

Cubre:
- EnergiaPayloadParser filtra fases de `acc` por fases_con_ti y marca `fuente`.
- IngestarTelemetriaUseCase decide `prioritario` por subtópico (energyio > acc)
  y pasa fases_con_ti del dispositivo al parser.
"""

from datetime import datetime, timezone
from typing import Any

from src.application.mappers.energia_parser import EnergiaPayloadParser
from src.application.use_cases.ingestar_telemetria import IngestarTelemetriaUseCase
from src.domain.telemetria.entities import AcumuladoEnergia, Dispositivo
from src.domain.telemetria.value_objects import EstadoDispositivo, MacAddress

AHORA = datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)


class _RepoDisp:
    def __init__(self, dispositivo: Dispositivo):
        self.dispositivos = {dispositivo.id: dispositivo}

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
        pass

    def listar(self, planta_id: str | None = None) -> list[Dispositivo]:
        return list(self.dispositivos.values())

    def contar_por_organizacion(self, organizacion_id: str) -> int:
        return len(self.dispositivos)


class _RepoTelem:
    def __init__(self):
        self.energias: list[tuple[AcumuladoEnergia, bool]] = []

    def guardar_instantanea(self, lectura) -> None:
        pass

    def guardar_energia(self, acumulado: AcumuladoEnergia, prioritario: bool = True) -> None:
        self.energias.append((acumulado, prioritario))

    def guardar_alerta(self, alerta) -> None:
        pass

    def listar_alertas(self, dispositivo_id=None, solo_abiertas=False, **kwargs) -> list:
        return []


def _dispositivo_monofasico() -> Dispositivo:
    return Dispositivo(
        id="dev-mono",
        device_uid=MacAddress("D48C49F03564"),
        nombre="Powermeter-Mono",
        tipo_instalacion="CONSUMO",
        fases_con_ti="R",
        estado=EstadoDispositivo.ONLINE,
    )


def _dispositivo_trifasico() -> Dispositivo:
    return Dispositivo(
        id="dev-tri",
        device_uid=MacAddress("F8B3B7C0BF2C"),
        nombre="Powermeter-Tri",
        tipo_instalacion="CONSUMO",
        fases_con_ti="R,S,T",
        estado=EstadoDispositivo.ONLINE,
    )


def _limpiar_caches() -> None:
    IngestarTelemetriaUseCase._device_cache.clear()
    IngestarTelemetriaUseCase._ultimos_heartbeats.clear()
    IngestarTelemetriaUseCase._ultimas_persistencias.clear()
    IngestarTelemetriaUseCase._filtro_persistencia.limpiar()


# --- EnergiaPayloadParser: filtro de fases y fuente ---------------------------------


def test_acc_sin_fases_con_ti_suma_todas_las_fases():
    payload: dict[str, Any] = {
        "t": 1789300338,
        "f": [{"n": "R", "a": 166.43, "r": -8.35}, {"n": "S", "a": 1.51, "r": 1.18}, {"n": "T", "a": 0.37, "r": 0.02}],
    }
    acumulado = EnergiaPayloadParser.parsear_acumulado(payload, "dev-tri", AHORA)
    assert acumulado.energia_activa_neta is not None
    assert round(acumulado.energia_activa_neta.kwh, 2) == round(166.43 + 1.51 + 0.37, 2)


def test_acc_monofasico_ignora_fases_sin_ti():
    """El medidor invitado (fases_con_ti='R') no debe sumar S y T aunque el
    payload las traiga: son energía fantasma del TI, no consumo real (H2)."""
    payload: dict[str, Any] = {
        "t": 1789300338,
        "f": [{"n": "R", "a": 166.43, "r": -8.35}, {"n": "S", "a": 1.51, "r": 1.18}, {"n": "T", "a": 0.37, "r": 0.02}],
    }
    acumulado = EnergiaPayloadParser.parsear_acumulado(payload, "dev-mono", AHORA, fases_con_ti={"R"})
    assert acumulado.energia_activa_neta is not None
    assert round(acumulado.energia_activa_neta.kwh, 2) == 166.43


def test_energyio_no_se_filtra_por_fases_ya_es_total_del_equipo():
    payload = {"t": 1789300338, "ae_imp": 168.94, "ae_exp": 0.01, "re_imp": 4.26, "re_exp": 10.01}
    acumulado = EnergiaPayloadParser.parsear_acumulado(
        payload, "dev-mono", AHORA, fases_con_ti={"R"}, fuente="energyio"
    )
    assert acumulado.energia_activa_importada is not None
    assert acumulado.energia_activa_importada.kwh == 168.94
    assert acumulado.fuente == "energyio"


def test_fuente_se_propaga_a_la_entidad():
    payload = {"t": 1789300338, "f": [{"n": "R", "a": 10.0}]}
    acumulado = EnergiaPayloadParser.parsear_acumulado(payload, "dev-mono", AHORA, fuente="acc")
    assert acumulado.fuente == "acc"


# --- IngestarTelemetriaUseCase: prioridad por subtópico (D1) ------------------------


def test_energyio_se_guarda_como_prioritario():
    _limpiar_caches()
    repo_disp = _RepoDisp(_dispositivo_monofasico())
    repo_telem = _RepoTelem()
    use_case = IngestarTelemetriaUseCase(repo_disp, repo_telem)

    payload = {"t": 1789300338, "ae_imp": 168.94, "ae_exp": 0.01}
    use_case.ejecutar("m/wifi/D48C49F03564/energyio", payload)

    assert len(repo_telem.energias) == 1
    acumulado, prioritario = repo_telem.energias[0]
    assert prioritario is True
    assert acumulado.fuente == "energyio"


def test_acc_se_guarda_como_respaldo_no_prioritario():
    _limpiar_caches()
    repo_disp = _RepoDisp(_dispositivo_monofasico())
    repo_telem = _RepoTelem()
    use_case = IngestarTelemetriaUseCase(repo_disp, repo_telem)

    payload = {"t": 1789300338, "f": [{"n": "R", "a": 166.43}]}
    use_case.ejecutar("m/wifi/D48C49F03564/acc", payload)

    assert len(repo_telem.energias) == 1
    acumulado, prioritario = repo_telem.energias[0]
    assert prioritario is False
    assert acumulado.fuente == "acc"


def test_acc_de_dispositivo_monofasico_ignora_fases_sin_ti_en_la_ingesta_real():
    _limpiar_caches()
    repo_disp = _RepoDisp(_dispositivo_monofasico())
    repo_telem = _RepoTelem()
    use_case = IngestarTelemetriaUseCase(repo_disp, repo_telem)

    payload = {
        "t": 1789300338,
        "f": [{"n": "R", "a": 166.43}, {"n": "S", "a": 1.51}, {"n": "T", "a": 0.37}],
    }
    use_case.ejecutar("m/wifi/D48C49F03564/acc", payload)

    acumulado, _ = repo_telem.energias[0]
    assert acumulado.energia_activa_neta is not None
    assert round(acumulado.energia_activa_neta.kwh, 2) == 166.43


def test_acc_de_dispositivo_trifasico_suma_las_tres_fases_en_la_ingesta_real():
    _limpiar_caches()
    repo_disp = _RepoDisp(_dispositivo_trifasico())
    repo_telem = _RepoTelem()
    use_case = IngestarTelemetriaUseCase(repo_disp, repo_telem)

    payload = {
        "t": 1789300338,
        "f": [{"n": "R", "a": 166.43}, {"n": "S", "a": 1.51}, {"n": "T", "a": 0.37}],
    }
    use_case.ejecutar("m/wifi/F8B3B7C0BF2C/acc", payload)

    acumulado, _ = repo_telem.energias[0]
    assert acumulado.energia_activa_neta is not None
    assert round(acumulado.energia_activa_neta.kwh, 2) == round(166.43 + 1.51 + 0.37, 2)


# --- Throttle de persistencia (WP3, D5, nivel ③) -------------------------------------


def test_energyio_dentro_de_la_ventana_no_se_persiste_dos_veces():
    _limpiar_caches()
    repo_disp = _RepoDisp(_dispositivo_monofasico())
    repo_telem = _RepoTelem()
    use_case = IngestarTelemetriaUseCase(repo_disp, repo_telem, granularidad_segundos=300)

    use_case.ejecutar("m/wifi/D48C49F03564/energyio", {"t": 1789300000, "ae_imp": 100.0})
    use_case.ejecutar("m/wifi/D48C49F03564/energyio", {"t": 1789300002, "ae_imp": 100.02})  # +2s, misma ventana

    assert len(repo_telem.energias) == 1
    acumulado, _ = repo_telem.energias[0]
    assert acumulado.energia_activa_importada.kwh == 100.0  # la segunda, dentro de la ventana, no llegó a persistir


def test_energyio_fuera_de_la_ventana_se_persiste_de_nuevo():
    _limpiar_caches()
    repo_disp = _RepoDisp(_dispositivo_monofasico())
    repo_telem = _RepoTelem()
    use_case = IngestarTelemetriaUseCase(repo_disp, repo_telem, granularidad_segundos=300)

    use_case.ejecutar("m/wifi/D48C49F03564/energyio", {"t": 1789300000, "ae_imp": 100.0})
    use_case.ejecutar("m/wifi/D48C49F03564/energyio", {"t": 1789300301, "ae_imp": 105.0})  # +301s

    assert len(repo_telem.energias) == 2


def test_acc_y_energyio_tienen_ventanas_de_throttle_independientes():
    """Si compartieran clave, el que llega primero en la ventana 'gana el turno'
    y descarta al otro aunque sea energyio (prioritario, D1) el que se pierde."""
    _limpiar_caches()
    repo_disp = _RepoDisp(_dispositivo_monofasico())
    repo_telem = _RepoTelem()
    use_case = IngestarTelemetriaUseCase(repo_disp, repo_telem, granularidad_segundos=300)

    use_case.ejecutar("m/wifi/D48C49F03564/acc", {"t": 1789300000, "f": [{"n": "R", "a": 100.0}]})
    use_case.ejecutar("m/wifi/D48C49F03564/energyio", {"t": 1789300002, "ae_imp": 100.5})

    assert len(repo_telem.energias) == 2
    fuentes = {acumulado.fuente for acumulado, _ in repo_telem.energias}
    assert fuentes == {"acc", "energyio"}
