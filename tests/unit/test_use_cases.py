from datetime import datetime

from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.application.use_cases.ingestar_telemetria import IngestarTelemetriaUseCase
from src.domain.telemetria.entities import (
    AcumuladoEnergia,
    AlertaDispositivo,
    Dispositivo,
    LecturaInstantanea,
    LogEstadoDispositivo,
)
from src.domain.telemetria.ports import (
    LoggerPort,
    RepositorioDispositivosPort,
    RepositorioTelemetriaPort,
)
from src.domain.telemetria.value_objects import MacAddress


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

    def guardar(self, dispositivo: Dispositivo) -> Dispositivo:
        self.dispositivos[dispositivo.id] = dispositivo
        return dispositivo


class MockTelemetriaRepo(RepositorioTelemetriaPort):
    def __init__(self):
        self.instantaneas: list[LecturaInstantanea] = []
        self.energias: list[AcumuladoEnergia] = []
        self.logs: list[LogEstadoDispositivo] = []
        self.alertas: list[AlertaDispositivo] = []

    def guardar_instantanea(self, lectura: LecturaInstantanea) -> None:
        self.instantaneas.append(lectura)

    def guardar_energia(self, acumulado: AcumuladoEnergia) -> None:
        self.energias.append(acumulado)

    def guardar_log_estado(self, log: LogEstadoDispositivo) -> None:
        self.logs.append(log)

    def guardar_alerta(self, alerta: AlertaDispositivo) -> None:
        self.alertas.append(alerta)

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
        self, dispositivo_id: str, limite: int, desde: datetime | None = None
    ) -> list[LecturaInstantanea]:
        return [i for i in self.instantaneas if i.dispositivo_id == dispositivo_id][:limite]

    def listar_energias(
        self, dispositivo_id: str, limite: int, desde: datetime | None = None
    ) -> list[AcumuladoEnergia]:
        return [e for e in self.energias if e.dispositivo_id == dispositivo_id][:limite]


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
