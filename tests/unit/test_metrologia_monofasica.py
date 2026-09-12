"""tests/unit/test_metrologia_monofasica.py — Pruebas de metrología monofásica (1P2W) y saneamiento de fases sin TI (specs/metrologia-monofasica.md)."""

from datetime import datetime, timezone
from typing import Any

from src.application.use_cases.ingestar_telemetria import IngestarTelemetriaUseCase
from src.domain.telemetria.entities import (
    Dispositivo,
    LecturaInstantanea,
    MedicionFase,
)
from src.domain.telemetria.services import AnalizadorCalidadEnergiaService
from src.domain.telemetria.value_objects import (
    Corriente,
    EstadoDispositivo,
    FactorPotencia,
    MacAddress,
    PotenciaActiva,
    PotenciaAparente,
    PotenciaReactiva,
    Tension,
)


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


def test_es_instalacion_monofasica_por_tipo_1p2w():
    assert AnalizadorCalidadEnergiaService.es_instalacion_monofasica("1P2W", "R,S,T") is True
    assert AnalizadorCalidadEnergiaService.es_instalacion_monofasica(" 1p2w ", "R,S,T") is True


def test_es_instalacion_monofasica_por_fase_unica():
    assert AnalizadorCalidadEnergiaService.es_instalacion_monofasica("CONSUMO", "R") is True


def test_es_instalacion_monofasica_falso_trifasico():
    assert AnalizadorCalidadEnergiaService.es_instalacion_monofasica("CONSUMO", "R,S,T") is False
    assert AnalizadorCalidadEnergiaService.es_instalacion_monofasica("3P4W", "R,S,T") is False


def test_es_instalacion_monofasica_falso_aron_2_ti():
    assert AnalizadorCalidadEnergiaService.es_instalacion_monofasica("3P3W", "R,T") is False
    assert AnalizadorCalidadEnergiaService.es_instalacion_monofasica("3P3W", "S,T") is False


def test_fases_con_ti_como_lista_normaliza():
    assert AnalizadorCalidadEnergiaService.fases_con_ti_como_lista("R,S,T") == {"R", "S", "T"}
    assert AnalizadorCalidadEnergiaService.fases_con_ti_como_lista(" r,t ") == {"R", "T"}
    assert AnalizadorCalidadEnergiaService.fases_con_ti_como_lista(["R", "T"]) == {"R", "T"}
    assert AnalizadorCalidadEnergiaService.fases_con_ti_como_lista(None) == {"R", "S", "T"}


def test_sanear_fase_sin_ti_conserva_tension_y_thd_v():
    fase = MedicionFase(
        tension=Tension(227.7),
        corriente=Corriente(0.9),
        potencia_activa=PotenciaActiva(147.0),
        potencia_reactiva=PotenciaReactiva(-51.0),
        potencia_aparente=PotenciaAparente(204.93),
        factor_potencia=FactorPotencia(0.72),
        thd_v_porcentaje=1.3,
        thd_i_porcentaje=8.4,
    )
    saneada = AnalizadorCalidadEnergiaService.sanear_fase_sin_ti(fase)

    assert saneada.tension is not None and saneada.tension.voltios == 227.7
    assert saneada.thd_v_porcentaje == 1.3
    assert saneada.corriente is None
    assert saneada.potencia_activa is None
    assert saneada.potencia_reactiva is None
    assert saneada.potencia_aparente is None
    assert saneada.factor_potencia is None
    assert saneada.thd_i_porcentaje is None


def test_ingesta_compacto_raiz_n_sin_replica():
    _limpiar_caches()
    repo_disp = _RepoDisp(_dispositivo_monofasico())
    repo_telem = _RepoTelem()
    use_case = IngestarTelemetriaUseCase(repo_disp, repo_telem)

    payload = {"t": 1788303000, "n": "R", "v": 227.7, "i": 0.9, "p": 147, "q": -51}

    use_case.ejecutar("m/wifi/D48C49F03564/inst", payload)

    assert len(repo_telem.instantaneas) == 1
    inst = repo_telem.instantaneas[0]
    assert inst.fase_r.tension is not None and inst.fase_r.tension.voltios == 227.7
    assert inst.fase_r.corriente is not None and inst.fase_r.corriente.amperios == 0.9
    # Sin réplica: S y T quedan vacías
    assert inst.fase_s.tension is None
    assert inst.fase_s.corriente is None
    assert inst.fase_t.tension is None
    assert inst.fase_t.corriente is None
    # Monofásico: métricas trifásicas anuladas
    assert inst.voltage_linea_V is None
    assert inst.desbalance_tension_porcentaje is None
    assert inst.corriente_neutro_estimada is None
    assert inst.tension_neutro_estimada is None


def test_ingesta_monofasico_sanea_fases_sin_ti_y_anula_metricas():
    _limpiar_caches()
    repo_disp = _RepoDisp(_dispositivo_monofasico())
    repo_telem = _RepoTelem()
    use_case = IngestarTelemetriaUseCase(repo_disp, repo_telem)

    payload = {
        "t": 1788302700,
        "f": [
            {"n": "R", "v": 227.7, "i": 0.9, "p": 147, "q": -51},
            {"n": "S", "v": 227.4, "i": 0.2, "p": 3, "q": 2},
            {"n": "T", "v": 228.5, "i": 0.1, "p": 1, "q": 5},
        ],
    }

    use_case.ejecutar("m/wifi/D48C49F03564/inst", payload)

    assert len(repo_telem.instantaneas) == 1
    inst = repo_telem.instantaneas[0]
    # R conserva todo (es la fase con TI)
    assert inst.fase_r.tension is not None and inst.fase_r.tension.voltios == 227.7
    assert inst.fase_r.corriente is not None and inst.fase_r.corriente.amperios == 0.9
    # S y T conservan tensión (paralelo) pero anulan corriente/P/Q/S/FP
    assert inst.fase_s.tension is not None and inst.fase_s.tension.voltios == 227.4
    assert inst.fase_s.corriente is None
    assert inst.fase_s.potencia_activa is None
    assert inst.fase_t.tension is not None and inst.fase_t.tension.voltios == 228.5
    assert inst.fase_t.corriente is None
    assert inst.fase_t.potencia_activa is None
    # Monofásico: métricas trifásicas anuladas
    assert inst.voltage_linea_V is None
    assert inst.desbalance_tension_porcentaje is None
    assert inst.corriente_neutro_estimada is None
    assert inst.tension_neutro_estimada is None
    # Total = solo la fase con TI
    assert inst.potencia_activa_total is not None and inst.potencia_activa_total.vatios == 147.0


def test_ingesta_monofasico_no_genera_alerta_desbalance():
    _limpiar_caches()
    repo_disp = _RepoDisp(_dispositivo_monofasico())
    repo_telem = _RepoTelem()
    use_case = IngestarTelemetriaUseCase(repo_disp, repo_telem)

    # Tensiones divergentes que en trifásico dispararían DESBALANCE_TENSION
    payload = {
        "t": 1788302700,
        "f": [
            {"n": "R", "v": 227.7, "i": 0.9, "p": 147, "q": -51},
            {"n": "S", "v": 180.0, "i": 0.2, "p": 3, "q": 2},
            {"n": "T", "v": 250.0, "i": 0.1, "p": 1, "q": 5},
        ],
    }

    # Dos lecturas consecutivas: en trifásico el filtro de persistencia confirmaría la alerta
    use_case.ejecutar("m/wifi/D48C49F03564/inst", payload)
    use_case.ejecutar("m/wifi/D48C49F03564/inst", payload)

    assert not [a for a in repo_telem.alertas if a.tipo_alerta == "DESBALANCE_TENSION"]


def test_agregar_lecturas_intervalo_monofasico_anula_metricas():
    t0 = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)

    l1 = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-mono",
        registrado_en=t0,
        fase_r=MedicionFase(tension=Tension(227.7), corriente=Corriente(0.9), potencia_activa=PotenciaActiva(147.0)),
        fase_s=MedicionFase(tension=Tension(227.4)),
        fase_t=MedicionFase(tension=Tension(228.5)),
        potencia_activa_total=PotenciaActiva(147.0),
        desbalance_tension_porcentaje=0.2,
        corriente_neutro_estimada=Corriente(0.1),
        voltage_linea_V=397.0,
        tension_neutro_estimada=0.0,
    )

    agregadas = AnalizadorCalidadEnergiaService.agregar_lecturas_en_intervalo(
        [l1], intervalo_segundos=60, es_monofasico=True
    )

    assert len(agregadas) == 1
    agg = agregadas[0]
    assert agg.desbalance_tension_porcentaje is None
    assert agg.corriente_neutro_estimada is None
    assert agg.voltage_linea_V is None
    assert agg.tension_neutro_estimada is None
