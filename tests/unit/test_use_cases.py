"""tests/unit/test_use_cases.py."""

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.application.use_cases.gestionar_maquinas import GestionarMaquinasUseCase
from src.application.use_cases.ingestar_telemetria import IngestarTelemetriaUseCase
from src.domain.disponibilidad.entities import Maquina
from src.domain.disponibilidad.exceptions import MaquinaNoEncontradaError
from src.domain.disponibilidad.ports import RepositorioMaquinasPort
from src.domain.telemetria.entities import (
    AcumuladoEnergia,
    AlertaDispositivo,
    Dispositivo,
    LecturaInstantanea,
    LogEstadoDispositivo,
    MedicionFase,
)
from src.domain.telemetria.ports import (
    LoggerPort,
    PublicadorEventosPort,
    RepositorioDispositivosPort,
    RepositorioTelemetriaPort,
)
from src.domain.telemetria.value_objects import (
    LecturaPotenciaTemporal,
    MacAddress,
    PotenciaActiva,
)


class MockMaquinasRepo(RepositorioMaquinasPort):
    def __init__(self):
        self.maquinas: dict[str, Maquina] = {}

    def obtener_por_id(self, maquina_id: str) -> Maquina | None:
        return self.maquinas.get(maquina_id)

    def obtener_por_dispositivo_id(self, dispositivo_id: str) -> Maquina | None:
        return next((m for m in self.maquinas.values() if m.dispositivo_id == dispositivo_id), None)

    def listar(self, organizacion_id: str | None = None) -> list[Maquina]:
        return list(self.maquinas.values())

    def guardar(self, maquina: Maquina) -> Maquina:
        self.maquinas[maquina.id] = maquina
        return maquina


class MockDispositivosRepo(RepositorioDispositivosPort):
    def __init__(self):
        self.dispositivos: dict[str, Dispositivo] = {}

    def obtener_por_id(self, dispositivo_id: str) -> Dispositivo | None:
        return self.dispositivos.get(dispositivo_id)

    def obtener_por_uid(self, uid: MacAddress) -> Dispositivo | None:
        for d in self.dispositivos.values():
            if d.device_uid.valor == uid.valor:
                return d
        return None

    def listar(self, planta_id: str | None = None) -> list[Dispositivo]:
        return list(self.dispositivos.values())

    def contar_por_organizacion(self, organizacion_id: str) -> int:
        return len(self.dispositivos)

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
            if numero_serie:
                d.numero_serie = numero_serie
            if version_fw:
                d.version_fw = version_fw
            if version_hw:
                d.version_hw = version_hw


class MockPublicadorEventos(PublicadorEventosPort):
    def __init__(self):
        self.eventos: list[tuple[str, dict[str, Any]]] = []

    def publicar_telemetria_en_vivo(self, topico: str, datos: dict[str, Any]) -> None:
        self.eventos.append((topico, datos))


class MockTelemetriaRepo(RepositorioTelemetriaPort):
    def __init__(self):
        self.instantaneas: list[LecturaInstantanea] = []
        self.energias: list[AcumuladoEnergia] = []
        self.logs: list[LogEstadoDispositivo] = []
        self.alertas: list[AlertaDispositivo] = []

    def guardar_instantanea(self, lectura: LecturaInstantanea) -> None:
        self.instantaneas.append(lectura)

    def guardar_energia(self, acumulado: AcumuladoEnergia, prioritario: bool = True) -> None:
        self.energias.append(acumulado)

    def guardar_log_estado(self, log: LogEstadoDispositivo) -> None:
        self.logs.append(log)

    def guardar_alerta(self, alerta: AlertaDispositivo) -> None:
        self.alertas.append(alerta)

    def listar_alertas(
        self,
        dispositivo_id: str | None = None,
        solo_abiertas: bool = False,
        severidad: str | None = None,
        limite: int = 100,
        desde: datetime | None = None,
        hasta: datetime | None = None,
    ) -> list[AlertaDispositivo]:
        q = list(self.alertas)
        if dispositivo_id:
            q = [a for a in q if a.dispositivo_id == dispositivo_id]
        if solo_abiertas:
            q = [a for a in q if not a.esta_resuelta]
        if severidad:
            q = [a for a in q if a.severidad.value == severidad.upper()]
        if desde:
            q = [a for a in q if a.disparada_en >= desde]
        if hasta:
            q = [a for a in q if a.disparada_en <= hasta]
        return q[:limite]

    def obtener_alerta_por_id(self, alerta_id: int) -> AlertaDispositivo | None:
        for a in self.alertas:
            if a.id == alerta_id:
                return a
        return None

    def obtener_ultima_instantanea(self, dispositivo_id: str) -> LecturaInstantanea | None:
        for inst in reversed(self.instantaneas):
            if inst.dispositivo_id == dispositivo_id:
                return inst
        return None

    def obtener_ultimo_acumulado(self, dispositivo_id: str) -> AcumuladoEnergia | None:
        for acc in reversed(self.energias):
            if acc.dispositivo_id == dispositivo_id:
                return acc
        return None

    def listar_instantaneas(
        self, dispositivo_id: str, limite: int, desde: datetime | None = None, hasta: datetime | None = None
    ) -> list[LecturaInstantanea]:
        return [i for i in self.instantaneas if i.dispositivo_id == dispositivo_id][:limite]

    def listar_energias(
        self, dispositivo_id: str, limite: int, desde: datetime | None = None
    ) -> list[AcumuladoEnergia]:
        return [e for e in self.energias if e.dispositivo_id == dispositivo_id][:limite]

    def listar_ultimos_acumulados_por_periodo(
        self, dispositivo_id: str, desde: datetime | None = None, granularidad: str = "day", zona: str = "UTC"
    ) -> list[AcumuladoEnergia]:
        return [e for e in self.energias if e.dispositivo_id == dispositivo_id]

    def listar_potencias_para_histograma(
        self, dispositivo_id: str, desde: datetime, limite: int | None = None
    ) -> list[LecturaPotenciaTemporal]:
        items = [
            LecturaPotenciaTemporal(momento=i.registrado_en, potencia_w=i.potencia_activa_total.vatios)
            for i in self.instantaneas
            if i.dispositivo_id == dispositivo_id and i.potencia_activa_total is not None and i.registrado_en >= desde
        ]
        items.sort(key=lambda x: x.momento)
        if limite is not None:
            items = items[:limite]
        return items

    def purgar_instantaneas_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        prev = len(self.instantaneas)
        self.instantaneas = [i for i in self.instantaneas if i.registrado_en >= fecha_limite]
        return prev - len(self.instantaneas)

    def purgar_energias_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        prev = len(self.energias)
        self.energias = [e for e in self.energias if e.registrado_en >= fecha_limite]
        return prev - len(self.energias)

    def purgar_status_logs_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        prev = len(self.logs)
        self.logs = [log_item for log_item in self.logs if log_item.registrado_en >= fecha_limite]
        return prev - len(self.logs)

    def purgar_alertas_resueltas_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        prev = len(self.alertas)
        self.alertas = [
            a for a in self.alertas if not (a.esta_resuelta and a.resuelta_en and a.resuelta_en < fecha_limite)
        ]
        return prev - len(self.alertas)

    def guardar_anomalia(self, device_id: str, error_s: float, recorded_at: datetime) -> None:
        pass

    def obtener_error_promedio(self, device_id: str, desde: datetime, hasta: datetime) -> float | None:
        return None


class MockLogger(LoggerPort):
    def __init__(self):
        self.logs: list[tuple[str, str, dict]] = []

    def info(self, evento: str, **kwargs: object) -> None:
        self.logs.append(("INFO", evento, dict(kwargs)))

    def warning(self, evento: str, **kwargs: object) -> None:
        self.logs.append(("WARNING", evento, dict(kwargs)))

    def error(self, evento: str, **kwargs: object) -> None:
        self.logs.append(("ERROR", evento, dict(kwargs)))

    def debug(self, evento: str, **kwargs: object) -> None:
        self.logs.append(("DEBUG", evento, dict(kwargs)))


def test_ingestar_telemetria_instantanea():
    repo_disp = MockDispositivosRepo()
    repo_telem = MockTelemetriaRepo()
    mock_logger = MockLogger()

    use_case = IngestarTelemetriaUseCase(repo_disp, repo_telem, logger=mock_logger)

    payload = {
        "timestamp": 1767377818,
        "phase_r": {"voltage_V": 226.9, "current_A": 0.1, "net_active_power_W": -4.4, "power_factor": -0.14},
        "phase_s": {"voltage_V": 227.0, "current_A": 0.2, "net_active_power_W": 7.7, "power_factor": 0.15},
        "phase_t": {"voltage_V": 227.5, "current_A": 0.2, "net_active_power_W": -0.7, "power_factor": -0.01},
        "total": {"net_active_power_W": 2.4, "power_factor": 0.16},
    }

    use_case.ejecutar("m/wifi/D48C49F03564/inst", payload)

    assert len(repo_disp.dispositivos) == 1
    assert len(repo_telem.instantaneas) == 1
    assert any(log[1] == "nuevo_dispositivo_registrado" for log in mock_logger.logs)

    consultar_uc = ConsultarTelemetriaUseCase(repo_telem, repo_disp)
    res = consultar_uc.obtener_ultima_telemetria("D48C49F03564")
    assert res.instantanea is not None
    assert res.instantanea.fase_r.voltage_V == 226.9
    assert res.instantanea.potencia_activa_total_W == 2.4
    assert res.instantanea.voltage_linea_V is not None
    assert res.instantanea.voltage_linea_V > 0
    assert res.instantanea.tension_neutro_estimada_V is not None


def test_ingestar_telemetria_compacta_inst():
    repo_disp = MockDispositivosRepo()
    repo_telem = MockTelemetriaRepo()
    mock_logger = MockLogger()

    use_case = IngestarTelemetriaUseCase(repo_disp, repo_telem, logger=mock_logger)

    payload = {
        "t": 1786737900,
        "a": 0,
        "f": [
            {"n": "R", "v": 223.4, "i": 0.0, "p": 0, "q": 0},
            {"n": "S", "v": 223.1, "i": 0.0, "p": 0, "q": 0},
            {"n": "T", "v": 223.9, "i": 0.0, "p": 0, "q": 0},
        ],
    }

    use_case.ejecutar("m/wifi/D48C49F03564/inst", payload)

    assert len(repo_telem.instantaneas) == 1
    inst = repo_telem.instantaneas[0]
    assert inst.fase_r.tension is not None and inst.fase_r.tension.voltios == 223.4
    assert inst.fase_s.tension is not None and inst.fase_s.tension.voltios == 223.1
    assert inst.fase_t.tension is not None and inst.fase_t.tension.voltios == 223.9
    assert inst.voltage_linea_V is not None
    assert inst.voltage_linea_V > 0
    assert inst.tension_neutro_estimada is not None
    # Sin carga: S = V·I = 0, y con S en cero el FP queda indefinido
    assert inst.fase_r.potencia_aparente is not None and inst.fase_r.potencia_aparente.va == 0.0
    assert inst.fase_r.factor_potencia is None


def test_ingestar_telemetria_compacta_deriva_potencia_aparente_y_fp():
    """El firmware compacto no publica S ni FP; el backend los deriva de V·I y P/S.

    Antes quedaban en null y la API igual afirmaba `estado_fp: OPTIMO`.
    """
    repo_disp = MockDispositivosRepo()
    repo_telem = MockTelemetriaRepo()
    use_case = IngestarTelemetriaUseCase(repo_disp, repo_telem, logger=MockLogger())

    # Valores reales medidos por el SmartPlus D48C49F03564
    payload = {
        "t": 1788302700,
        "a": 0,
        "f": [
            {"n": "R", "v": 227.7, "i": 0.9, "p": 147, "q": -51},
            {"n": "S", "v": 227.4, "i": 0.0, "p": 0, "q": 2},
            {"n": "T", "v": 228.5, "i": 0.1, "p": 1, "q": 5},
        ],
    }

    use_case.ejecutar("m/wifi/D48C49F03564/inst", payload)

    inst = repo_telem.instantaneas[0]
    assert inst.fase_r.potencia_aparente is not None
    assert inst.fase_r.potencia_aparente.va == 204.93
    assert inst.fase_r.factor_potencia is not None
    assert inst.fase_r.factor_potencia.valor == 0.72
    assert inst.potencia_aparente_total is not None
    assert inst.potencia_aparente_total.va == 227.78
    assert inst.factor_potencia_total is not None


def test_ingestar_telemetria_no_rompe_si_p_supera_v_por_i():
    """V e I llegan redondeados del firmware; P se mide aparte y puede exceder V·I.

    Sin acotar el cociente, `FactorPotencia` lanza y se pierde la lectura entera.
    """
    repo_telem = MockTelemetriaRepo()
    use_case = IngestarTelemetriaUseCase(MockDispositivosRepo(), repo_telem, logger=MockLogger())

    payload = {
        "t": 1788303000,
        "a": 0,
        "f": [{"n": "R", "v": 100.0, "i": 1.0, "p": 250, "q": 0}],
    }

    use_case.ejecutar("m/wifi/AA11BB22CC33/inst", payload)

    inst = repo_telem.instantaneas[0]
    assert inst.fase_r.factor_potencia is not None
    assert inst.fase_r.factor_potencia.valor == 1.0


def test_ingestar_telemetria_compacta_acc():
    repo_disp = MockDispositivosRepo()
    repo_telem = MockTelemetriaRepo()
    mock_logger = MockLogger()

    use_case = IngestarTelemetriaUseCase(repo_disp, repo_telem, logger=mock_logger)

    payload = {
        "t": 1786737600,
        "a": 0,
        "f": [
            {"n": "R", "a": 0.03, "r": 0.01},
            {"n": "S", "a": 0.02, "r": 0.00},
            {"n": "T", "a": 0.03, "r": 0.01},
        ],
    }

    use_case.ejecutar("m/wifi/D48C49F03564/acc", payload)

    assert len(repo_telem.energias) == 1
    acc = repo_telem.energias[0]
    assert acc.energia_activa_neta is not None
    assert round(acc.energia_activa_neta.kwh, 2) == 0.08
    assert acc.energia_reactiva_neta is not None
    assert round(acc.energia_reactiva_neta.kvarh, 2) == 0.02


def test_ingestar_telemetria_calcula_y_persiste_desbalance_vur():
    IngestarTelemetriaUseCase._device_cache.clear()
    IngestarTelemetriaUseCase._filtro_persistencia.limpiar()
    repo_disp = MockDispositivosRepo()
    repo_telem = MockTelemetriaRepo()
    mock_logger = MockLogger()

    use_case = IngestarTelemetriaUseCase(repo_disp, repo_telem, logger=mock_logger)

    # V_prom = 220V, V_R=230, V_S=220, V_T=210 -> VUR = 4.55% (>3% -> CRITICAL)
    payload_1 = {
        "timestamp": 1767377820,
        "phase_r": {"voltage_V": 230.0, "current_A": 1.0, "net_active_power_W": 230.0},
        "phase_s": {"voltage_V": 220.0, "current_A": 1.0, "net_active_power_W": 220.0},
        "phase_t": {"voltage_V": 210.0, "current_A": 1.0, "net_active_power_W": 210.0},
        "total": {"net_active_power_W": 660.0},
    }
    # Lectura 1: se calcula y persiste desbalance, el filtro espera confirmación
    use_case.ejecutar("m/wifi/D48C49F03564/inst", payload_1)

    assert len(repo_telem.instantaneas) == 1
    inst = repo_telem.instantaneas[0]
    assert inst.desbalance_tension_porcentaje == 4.55
    assert inst.voltage_linea_V is not None
    assert inst.voltage_linea_V > 0
    assert inst.tension_neutro_estimada == 5.77

    # Comprobar consulta DTO
    consultar_uc = ConsultarTelemetriaUseCase(repo_telem, repo_disp)
    res = consultar_uc.obtener_ultima_telemetria("D48C49F03564")
    assert res.instantanea is not None
    assert res.instantanea.desbalance_tension_porcentaje == 4.55
    assert res.instantanea.voltage_linea_V is not None
    assert res.instantanea.voltage_linea_V > 0
    assert res.instantanea.tension_neutro_estimada_V == 5.77

    # Lectura 2: persistencia de desbalance continuo confirma la anomalía
    payload_2 = {
        "timestamp": 1767377821,
        "phase_r": {"voltage_V": 230.0, "current_A": 1.0, "net_active_power_W": 230.0},
        "phase_s": {"voltage_V": 220.0, "current_A": 1.0, "net_active_power_W": 220.0},
        "phase_t": {"voltage_V": 210.0, "current_A": 1.0, "net_active_power_W": 210.0},
        "total": {"net_active_power_W": 660.0},
    }
    use_case.ejecutar("m/wifi/D48C49F03564/inst", payload_2)

    # Comprobar generación de alerta de desbalance crítico
    alertas = repo_telem.listar_alertas()
    desbalance_alerts = [a for a in alertas if a.tipo_alerta == "DESBALANCE_TENSION"]
    assert len(desbalance_alerts) == 1
    assert desbalance_alerts[0].severidad.value == "CRITICAL"
    assert "4.55%" in desbalance_alerts[0].mensaje


def test_ingestar_telemetria_filtro_persistencia_transitorio():
    IngestarTelemetriaUseCase._device_cache.clear()
    IngestarTelemetriaUseCase._filtro_persistencia.limpiar()
    repo_disp = MockDispositivosRepo()
    repo_telem = MockTelemetriaRepo()

    use_case = IngestarTelemetriaUseCase(repo_disp, repo_telem)

    # Paquete 1 (t=0s): Subtensión simétrica transitoria por arranque de motor trifásico (V_R,S,T = 195V)
    payload_transitorio = {
        "timestamp": 1767377800,
        "phase_r": {"voltage_V": 195.0, "current_A": 10.0, "net_active_power_W": 1950.0},
        "phase_s": {"voltage_V": 195.0, "current_A": 10.0, "net_active_power_W": 1950.0},
        "phase_t": {"voltage_V": 195.0, "current_A": 10.0, "net_active_power_W": 1950.0},
    }
    use_case.ejecutar("m/wifi/D48C49F03564/inst", payload_transitorio)

    # 1 sola lectura: el filtro anti-falsos positivos bloquea la alerta
    assert len(repo_telem.listar_alertas()) == 0

    # Paquete 2 (t=1s): Tensión se normaliza a 220V
    payload_normal = {
        "timestamp": 1767377801,
        "phase_r": {"voltage_V": 220.0, "current_A": 1.0, "net_active_power_W": 220.0},
        "phase_s": {"voltage_V": 220.0, "current_A": 1.0, "net_active_power_W": 220.0},
        "phase_t": {"voltage_V": 220.0, "current_A": 1.0, "net_active_power_W": 220.0},
    }
    use_case.ejecutar("m/wifi/D48C49F03564/inst", payload_normal)
    assert len(repo_telem.listar_alertas()) == 0

    # Paquete 3 (t=10s): Nueva subtensión (lectura 1 del nuevo episodio)
    payload_sub_1 = {
        "timestamp": 1767377810,
        "phase_r": {"voltage_V": 194.0, "current_A": 1.0, "net_active_power_W": 194.0},
        "phase_s": {"voltage_V": 194.0, "current_A": 1.0, "net_active_power_W": 194.0},
        "phase_t": {"voltage_V": 194.0, "current_A": 1.0, "net_active_power_W": 194.0},
    }
    use_case.ejecutar("m/wifi/D48C49F03564/inst", payload_sub_1)
    assert len(repo_telem.listar_alertas()) == 0

    # Paquete 4 (t=11s): Subtensión continua (lectura 2 consecutiva) -> DISPARA alerta
    payload_sub_2 = {
        "timestamp": 1767377811,
        "phase_r": {"voltage_V": 194.0, "current_A": 1.0, "net_active_power_W": 194.0},
        "phase_s": {"voltage_V": 194.0, "current_A": 1.0, "net_active_power_W": 194.0},
        "phase_t": {"voltage_V": 194.0, "current_A": 1.0, "net_active_power_W": 194.0},
    }
    use_case.ejecutar("m/wifi/D48C49F03564/inst", payload_sub_2)

    alertas_tension = [a for a in repo_telem.listar_alertas() if a.tipo_alerta == "BAJA_TENSION"]
    assert len(alertas_tension) == 1
    assert alertas_tension[0].severidad.value == "WARNING"
    # Verificar que voltage_linea_V se calcula correctamente en el último episodio
    ultima_inst = repo_telem.instantaneas[-1]
    assert ultima_inst.voltage_linea_V is not None
    assert ultima_inst.voltage_linea_V > 0


def test_consultar_telemetria_granularidad_y_bucketing():
    from datetime import datetime, timedelta, timezone

    from src.domain.telemetria.entities import Dispositivo, LecturaInstantanea, MedicionFase
    from src.domain.telemetria.value_objects import Corriente, MacAddress, PotenciaActiva, Tension

    repo_disp = MockDispositivosRepo()
    repo_telem = MockTelemetriaRepo()

    dev = Dispositivo(
        id="dev-bucket",
        device_uid=MacAddress("D48C49F03564"),
        nombre="Medidor Bucket",
    )
    repo_disp.guardar(dev)

    ahora = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)

    # 4 lecturas en dos buckets de 5 minutos:
    # Bucket 1 (11:50 - 11:55): t=11:51 y t=11:53
    l1 = LecturaInstantanea(
        id=None,
        dispositivo_id=dev.id,
        registrado_en=ahora - timedelta(minutes=9),
        fase_r=MedicionFase(tension=Tension(220.0), corriente=Corriente(10.0), potencia_activa=PotenciaActiva(2200.0)),
        fase_s=MedicionFase(tension=Tension(220.0), corriente=Corriente(10.0), potencia_activa=PotenciaActiva(2200.0)),
        fase_t=MedicionFase(tension=Tension(220.0), corriente=Corriente(10.0), potencia_activa=PotenciaActiva(2200.0)),
        potencia_activa_total=PotenciaActiva(6600.0),
    )
    l2 = LecturaInstantanea(
        id=None,
        dispositivo_id=dev.id,
        registrado_en=ahora - timedelta(minutes=7),
        fase_r=MedicionFase(tension=Tension(230.0), corriente=Corriente(12.0), potencia_activa=PotenciaActiva(2760.0)),
        fase_s=MedicionFase(tension=Tension(220.0), corriente=Corriente(10.0), potencia_activa=PotenciaActiva(2200.0)),
        fase_t=MedicionFase(tension=Tension(210.0), corriente=Corriente(8.0), potencia_activa=PotenciaActiva(1680.0)),
        potencia_activa_total=PotenciaActiva(6640.0),
    )
    # Bucket 2 (11:55 - 12:00): t=11:56 y t=11:58
    l3 = LecturaInstantanea(
        id=None,
        dispositivo_id=dev.id,
        registrado_en=ahora - timedelta(minutes=4),
        fase_r=MedicionFase(tension=Tension(224.0), corriente=Corriente(10.0), potencia_activa=PotenciaActiva(2240.0)),
        fase_s=MedicionFase(tension=Tension(224.0), corriente=Corriente(10.0), potencia_activa=PotenciaActiva(2240.0)),
        fase_t=MedicionFase(tension=Tension(224.0), corriente=Corriente(10.0), potencia_activa=PotenciaActiva(2240.0)),
        potencia_activa_total=PotenciaActiva(6720.0),
    )
    l4 = LecturaInstantanea(
        id=None,
        dispositivo_id=dev.id,
        registrado_en=ahora - timedelta(minutes=2),
        fase_r=MedicionFase(tension=Tension(226.0), corriente=Corriente(10.0), potencia_activa=PotenciaActiva(2260.0)),
        fase_s=MedicionFase(tension=Tension(226.0), corriente=Corriente(10.0), potencia_activa=PotenciaActiva(2260.0)),
        fase_t=MedicionFase(tension=Tension(226.0), corriente=Corriente(10.0), potencia_activa=PotenciaActiva(2260.0)),
        potencia_activa_total=PotenciaActiva(6780.0),
    )

    repo_telem.guardar_instantanea(l1)
    repo_telem.guardar_instantanea(l2)
    repo_telem.guardar_instantanea(l3)
    repo_telem.guardar_instantanea(l4)

    consultar_uc = ConsultarTelemetriaUseCase(repo_telem, repo_disp)

    # 1. Consulta 'raw' -> retorna las 4 lecturas
    res_raw = consultar_uc.listar_instantaneas(dev.id, limite=100, granularidad="raw")
    assert len(res_raw) == 4

    # 2. Consulta '5m' -> remuestrea en 2 buckets
    res_5m = consultar_uc.listar_instantaneas(dev.id, limite=100, granularidad="5m")
    assert len(res_5m) == 2
    # El más reciente (11:55) primero: promedio de 6720 y 6780 -> 6750
    assert res_5m[0].potencia_activa_total_W == 6750.0
    # El anterior (11:50): promedio de 6600 y 6640 -> 6620
    assert res_5m[1].potencia_activa_total_W == 6620.0

    # 3. Consulta 'auto' con hours=2 (<=2) -> usa '1m'
    res_auto_2h = consultar_uc.listar_instantaneas(dev.id, limite=100, granularidad="auto", horas=2)
    # En 1m, cada lectura cayó en un minuto distinto -> 4 buckets de 1m
    assert len(res_auto_2h) == 4

    # 4. Consulta 'auto' con hours=24 (2 < hours <= 24) -> usa '5m'
    res_auto_24h = consultar_uc.listar_instantaneas(dev.id, limite=100, granularidad="auto", horas=24)
    assert len(res_auto_24h) == 2

    # 5. Consulta 'lttb' con limite=3 -> downsampling preservando el pico de potencia
    l_pico = LecturaInstantanea(
        id=None,
        dispositivo_id=dev.id,
        registrado_en=ahora - timedelta(minutes=20),
        fase_r=MedicionFase(),
        fase_s=MedicionFase(),
        fase_t=MedicionFase(),
        potencia_activa_total=PotenciaActiva(150000.0),
    )
    repo_telem.guardar_instantanea(l_pico)
    res_lttb = consultar_uc.listar_instantaneas(dev.id, limite=3, granularidad="lttb")
    assert len(res_lttb) == 3
    potencias_lttb = [r.potencia_activa_total_W for r in res_lttb if r.potencia_activa_total_W is not None]
    assert 150000.0 in potencias_lttb


class FakeBufferTelemetriaEnVivo:
    """Fake plano del puerto `BufferTelemetriaEnVivoPort` para tests."""

    def __init__(self, por_dispositivo: dict[str, list[dict]] | None = None):
        self._por_dispositivo = por_dispositivo or {}

    def obtener(self, dispositivo_id: str) -> list[dict]:
        return self._por_dispositivo.get(dispositivo_id, [])


def _lectura_buffer_dto(registrado_en: str, dispositivo_id: str = "dev-buffer") -> dict:
    fase_vacia = {"voltage_V": None, "current_A": None}
    return {
        "dispositivo_id": dispositivo_id,
        "registrado_en": registrado_en,
        "fase_r": fase_vacia,
        "fase_s": fase_vacia,
        "fase_t": fase_vacia,
        "potencia_activa_total_W": 500.0,
    }


def test_listar_instantaneas_antepone_lecturas_del_buffer_en_vivo():
    from datetime import datetime, timezone

    from src.domain.telemetria.entities import Dispositivo, LecturaInstantanea, MedicionFase
    from src.domain.telemetria.value_objects import MacAddress, PotenciaActiva

    repo_disp = MockDispositivosRepo()
    repo_telem = MockTelemetriaRepo()

    dev = Dispositivo(id="dev-buffer", device_uid=MacAddress("D48C49F03564"), nombre="Medidor Buffer")
    repo_disp.guardar(dev)

    persistida = LecturaInstantanea(
        id=1,
        dispositivo_id=dev.id,
        registrado_en=datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc),
        fase_r=MedicionFase(),
        fase_s=MedicionFase(),
        fase_t=MedicionFase(),
        potencia_activa_total=PotenciaActiva(700.0),
    )
    repo_telem.guardar_instantanea(persistida)

    buffer = FakeBufferTelemetriaEnVivo(
        {
            "dev-buffer": [
                _lectura_buffer_dto("2026-08-17T12:00:00Z"),  # ya está en BD -> se descarta (dedup)
                _lectura_buffer_dto("2026-08-17T12:03:00Z"),  # más reciente que BD -> se antepone
            ]
        }
    )
    consultar_uc = ConsultarTelemetriaUseCase(repo_telem, repo_disp, buffer_en_vivo=buffer)

    resultado = consultar_uc.listar_instantaneas(dev.id, limite=100, granularidad="raw")

    assert [r.registrado_en.isoformat() for r in resultado] == [
        "2026-08-17T12:03:00+00:00",
        "2026-08-17T12:00:00+00:00",
    ]


def test_listar_instantaneas_respeta_limite_tras_mezclar_buffer():
    from datetime import datetime, timezone

    from src.domain.telemetria.entities import Dispositivo, LecturaInstantanea, MedicionFase
    from src.domain.telemetria.value_objects import MacAddress, PotenciaActiva

    repo_disp = MockDispositivosRepo()
    repo_telem = MockTelemetriaRepo()

    dev = Dispositivo(id="dev-buffer-2", device_uid=MacAddress("AABBCCDDEEFF"), nombre="Medidor Buffer 2")
    repo_disp.guardar(dev)

    repo_telem.guardar_instantanea(
        LecturaInstantanea(
            id=1,
            dispositivo_id=dev.id,
            registrado_en=datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc),
            fase_r=MedicionFase(),
            fase_s=MedicionFase(),
            fase_t=MedicionFase(),
            potencia_activa_total=PotenciaActiva(700.0),
        )
    )

    buffer = FakeBufferTelemetriaEnVivo({"dev-buffer-2": [_lectura_buffer_dto("2026-08-17T12:03:00Z", "dev-buffer-2")]})
    consultar_uc = ConsultarTelemetriaUseCase(repo_telem, repo_disp, buffer_en_vivo=buffer)

    resultado = consultar_uc.listar_instantaneas(dev.id, limite=1, granularidad="raw")

    assert len(resultado) == 1
    assert resultado[0].registrado_en.isoformat() == "2026-08-17T12:03:00+00:00"


def test_jerarquia_falta_fase_inhibe_desbalance():

    repo_disp = MockDispositivosRepo()
    repo_telem = MockTelemetriaRepo()
    pub = MockPublicadorEventos()
    use_case = IngestarTelemetriaUseCase(repo_disp, repo_telem, publicador=pub)

    # 1. Falta de Fase en Fase S (Vs = 10.0V < 50V)
    # Jerarquía: Solo debe emitir FALTA_FASE, inhibiendo DESBALANCE_TENSION
    payload_corte_1 = {
        "timestamp": 1767377900,
        "phase_r": {"voltage_V": 220.0, "current_A": 10.0, "net_active_power_W": 2200.0},
        "phase_s": {"voltage_V": 10.0, "current_A": 0.0, "net_active_power_W": 0.0},
        "phase_t": {"voltage_V": 220.0, "current_A": 10.0, "net_active_power_W": 2200.0},
    }
    use_case.ejecutar("m/wifi/D48C49F03564/inst", payload_corte_1)

    payload_corte_2 = {
        "timestamp": 1767377901,
        "phase_r": {"voltage_V": 220.0, "current_A": 10.0, "net_active_power_W": 2200.0},
        "phase_s": {"voltage_V": 10.0, "current_A": 0.0, "net_active_power_W": 0.0},
        "phase_t": {"voltage_V": 220.0, "current_A": 10.0, "net_active_power_W": 2200.0},
    }
    use_case.ejecutar("m/wifi/D48C49F03564/inst", payload_corte_2)

    alertas = repo_telem.listar_alertas()
    tipos = [a.tipo_alerta for a in alertas]
    assert "FALTA_FASE" in tipos
    assert "DESBALANCE_TENSION" not in tipos


def test_autodespeje_alertas_y_websocket_broadcast():
    repo_disp = MockDispositivosRepo()
    repo_telem = MockTelemetriaRepo()
    pub = MockPublicadorEventos()
    use_case = IngestarTelemetriaUseCase(repo_disp, repo_telem, publicador=pub)

    # 1. Disparar subtensión simétrica (2 lecturas consecutivas a 192V en R, S, T)
    p1 = {
        "timestamp": 1767378000,
        "phase_r": {"voltage_V": 192.0, "current_A": 5.0, "net_active_power_W": 960.0},
        "phase_s": {"voltage_V": 192.0, "current_A": 5.0, "net_active_power_W": 960.0},
        "phase_t": {"voltage_V": 192.0, "current_A": 5.0, "net_active_power_W": 960.0},
    }
    p2 = {
        "timestamp": 1767378001,
        "phase_r": {"voltage_V": 192.0, "current_A": 5.0, "net_active_power_W": 960.0},
        "phase_s": {"voltage_V": 192.0, "current_A": 5.0, "net_active_power_W": 960.0},
        "phase_t": {"voltage_V": 192.0, "current_A": 5.0, "net_active_power_W": 960.0},
    }
    use_case.ejecutar("m/wifi/D48C49F03564/inst", p1)
    use_case.ejecutar("m/wifi/D48C49F03564/inst", p2)

    assert len(repo_telem.listar_alertas(solo_abiertas=True)) == 1

    # 2. Se normaliza la tensión a 220V simétrico -> Auto-despeje automático y broadcast WS
    p_normal = {
        "timestamp": 1767378020,
        "phase_r": {"voltage_V": 220.0, "current_A": 5.0, "net_active_power_W": 1100.0},
        "phase_s": {"voltage_V": 220.0, "current_A": 5.0, "net_active_power_W": 1100.0},
        "phase_t": {"voltage_V": 220.0, "current_A": 5.0, "net_active_power_W": 1100.0},
    }
    use_case.ejecutar("m/wifi/D48C49F03564/inst", p_normal)

    assert len(repo_telem.listar_alertas(solo_abiertas=True)) == 0
    alerta_resuelta = repo_telem.listar_alertas()[0]
    assert alerta_resuelta.esta_resuelta is True
    assert alerta_resuelta.duracion_segundos == 20.0

    # Verificar que se emitió el evento de resolución en vivo
    topicos = [t for t, _ in pub.eventos]
    assert "m/wifi/D48C49F03564/alertas" in topicos
    ultimo_evento = [d for t, d in pub.eventos if t == "m/wifi/D48C49F03564/alertas"][-1]
    assert ultimo_evento["esta_resuelta"] is True
    assert ultimo_evento["duracion_segundos"] == 20.0


def test_actualizar_dispositivo_campos_metrologia_y_patch():
    from src.application.dtos.dispositivo_dto import DispositivoActualizarDTO
    from src.application.use_cases.gestionar_dispositivos import GestionarDispositivosUseCase
    from src.domain.telemetria.entities import Planta
    from src.domain.telemetria.ports import RepositorioOrganizacionesPort

    class MockOrgRepo(RepositorioOrganizacionesPort):
        def obtener_por_id(self, organizacion_id: str):
            return None

        def listar_organizaciones(self):
            return []

        def guardar_organizacion(self, org):
            return org

        def obtener_planta_por_id(self, planta_id: str):
            return Planta(id=planta_id, organizacion_id="org-1", nombre="Planta Central")

        def listar_plantas(self, organizacion_id=None):
            return []

        def guardar_planta(self, planta):
            return planta

        def obtener_nodos_unifilar(self, planta_id: str):
            return []

        def guardar_nodos_unifilar(self, planta_id: str, nodos):
            return nodos

        def obtener_zonas_planta(self, planta_id: str):
            return []

        def obtener_dispositivos_layout(self, planta_id: str):
            return []

        def obtener_instalacion_medidor(self, dispositivo_id: str):
            return None

        def guardar_layout_planta(self, planta_id: str, plano_svg_url, zonas, dispositivos):
            pass

    repo_disp = MockDispositivosRepo()
    repo_org = MockOrgRepo()
    dev = Dispositivo(
        id="dev-123",
        device_uid=MacAddress("D48C49F03564"),
        nombre="Medidor Original",
        numero_serie="SN-OLD-001",
        tipo_instalacion="CONSUMO",
        fases_con_ti="R,S,T",
    )
    repo_disp.guardar(dev)

    use_case = GestionarDispositivosUseCase(repo_disp, repo_org)

    # Actualización parcial vía DTO (PATCH / PUT)
    dto_patch = DispositivoActualizarDTO(
        nombre="Inyectoras 1 a 4",
        ubicacion_tag="Nave 2 · Sala de Celdas BT · TGBT-02",
        numero_serie="SN-98234-DM",
        tipo_instalacion="3P4W",
        fases_con_ti="R,S,T",
        planta_id="planta-1",
    )
    res = use_case.actualizar_dispositivo("dev-123", dto_patch)

    assert res.id == "dev-123"
    assert res.nombre == "Inyectoras 1 a 4"
    assert res.ubicacion_tag == "Nave 2 · Sala de Celdas BT · TGBT-02"
    assert res.numero_serie == "SN-98234-DM"
    assert res.tipo_instalacion == "3P4W"
    assert res.fases_con_ti == "R,S,T"
    assert res.planta_id == "planta-1"

    # Verificar persistencia en repo
    guardado = repo_disp.obtener_por_id("dev-123")
    assert guardado is not None
    assert guardado.nombre == "Inyectoras 1 a 4"
    assert guardado.numero_serie == "SN-98234-DM"
    assert guardado.tipo_instalacion == "3P4W"


def test_consultar_telemetria_con_analitica_calidad_energia():
    from src.domain.telemetria.entities import MedicionFase
    from src.domain.telemetria.value_objects import (
        Corriente,
        FactorPotencia,
        PotenciaActiva,
        Tension,
    )

    repo_disp = MockDispositivosRepo()
    repo_telem = MockTelemetriaRepo()

    dev = Dispositivo(
        id="dev-analitica-1",
        device_uid=MacAddress("A1B2C3D4E5F6"),
        nombre="Medidor TGBT Planta Industrial",
    )
    repo_disp.guardar(dev)

    lectura = LecturaInstantanea(
        id=1,
        dispositivo_id="dev-analitica-1",
        registrado_en=datetime.now(),
        fase_r=MedicionFase(
            tension=Tension(215.0), corriente=Corriente(190.0), potencia_activa=PotenciaActiva(40000.0)
        ),
        fase_s=MedicionFase(
            tension=Tension(220.0), corriente=Corriente(180.0), potencia_activa=PotenciaActiva(40000.0)
        ),
        fase_t=MedicionFase(
            tension=Tension(225.0), corriente=Corriente(170.0), potencia_activa=PotenciaActiva(40000.0)
        ),
        potencia_activa_total=PotenciaActiva(120000.0),  # 120 kW
        factor_potencia_total=FactorPotencia(0.82),
        desbalance_tension_porcentaje=2.27,
    )
    repo_telem.guardar_instantanea(lectura)

    consultar_uc = ConsultarTelemetriaUseCase(repo_telem, repo_disp)
    res = consultar_uc.obtener_ultima_telemetria("dev-analitica-1")

    assert res.instantanea is not None
    assert res.analitica is not None
    assert res.instantanea.analitica is not None
    assert res.analitica.requiere_compensacion is True
    assert res.analitica.potencia_reactiva_a_compensar_kvar is not None
    assert res.analitica.potencia_reactiva_a_compensar_kvar > 0
    assert res.analitica.banco_sugerido_kvar is not None
    assert res.analitica.banco_sugerido_kvar >= res.analitica.potencia_reactiva_a_compensar_kvar
    assert res.analitica.penalizacion_estimada_ars is not None
    assert res.analitica.penalizacion_estimada_ars > 0
    assert res.analitica.desbalance_tension_porcentaje == 2.27
    assert res.analitica.desbalance_corriente_porcentaje is not None
    assert res.analitica.estado_fp == "PENALIZADO"
    assert res.analitica.estado_tension == "NORMAL"

    # Verificar historial de instantáneas
    historial = consultar_uc.listar_instantaneas("dev-analitica-1", limite=10)
    assert len(historial) == 1
    assert historial[0].analitica is not None
    assert historial[0].analitica.requiere_compensacion is True


def test_gestionar_maquinas_calcular_histograma_maquina_no_encontrada():
    repo_maq = MockMaquinasRepo()
    repo_telem = MockTelemetriaRepo()
    uc = GestionarMaquinasUseCase(repo_maq, repo_telem)

    with pytest.raises(MaquinaNoEncontradaError):
        uc.calcular_histograma("maq-inexistente")


def test_gestionar_maquinas_calcular_histograma_exitoso():
    repo_maq = MockMaquinasRepo()
    repo_telem = MockTelemetriaRepo()
    maquina = Maquina(id="maq-1", dispositivo_id="dev-1", nombre="Torno CNC")
    repo_maq.guardar(maquina)

    ahora = datetime.now(timezone.utc)
    for i in range(15):
        repo_telem.guardar_instantanea(
            LecturaInstantanea(
                id=i,
                dispositivo_id="dev-1",
                registrado_en=ahora - timedelta(minutes=60 - i),
                fase_r=MedicionFase(),
                fase_s=MedicionFase(),
                fase_t=MedicionFase(),
                potencia_activa_total=PotenciaActiva(50.0 + (i % 3)),
            )
        )
    for i in range(15, 30):
        repo_telem.guardar_instantanea(
            LecturaInstantanea(
                id=i,
                dispositivo_id="dev-1",
                registrado_en=ahora - timedelta(minutes=60 - i),
                fase_r=MedicionFase(),
                fase_s=MedicionFase(),
                fase_t=MedicionFase(),
                potencia_activa_total=PotenciaActiva(2000.0 + (i % 5)),
            )
        )

    uc = GestionarMaquinasUseCase(repo_maq, repo_telem)
    res = uc.calcular_histograma("maq-1", dias=7)

    assert res.dispositivo_id == "dev-1"
    assert res.dias_analizados == 7
    assert res.cantidad_lecturas == 30
    assert len(res.bordes_bins_w) == len(res.frecuencias) + 1
    assert res.escala == "logaritmica"
    assert res.lecturas_truncadas is False
    assert len(res.regimenes) >= 2
    assert res.umbral_sugerido_w is not None
    assert 50.0 < res.umbral_sugerido_w < 2000.0


def test_gestionar_maquinas_calcular_histograma_detecta_truncamiento():
    repo_maq = MockMaquinasRepo()
    repo_telem = MockTelemetriaRepo()
    maquina = Maquina(id="maq-2", dispositivo_id="dev-2", nombre="Fresadora")
    repo_maq.guardar(maquina)

    ahora = datetime.now(timezone.utc)
    for i in range(25):
        repo_telem.guardar_instantanea(
            LecturaInstantanea(
                id=i,
                dispositivo_id="dev-2",
                registrado_en=ahora - timedelta(minutes=50 - i),
                fase_r=MedicionFase(),
                fase_s=MedicionFase(),
                fase_t=MedicionFase(),
                potencia_activa_total=PotenciaActiva(100.0 + i),
            )
        )

    uc = GestionarMaquinasUseCase(repo_maq, repo_telem)
    res = uc.calcular_histograma("maq-2", dias=7, limite=20)

    assert res.cantidad_lecturas == 20
    assert res.lecturas_truncadas is True
