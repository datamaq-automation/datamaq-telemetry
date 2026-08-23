from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.application.dtos.dispositivo_dto import DispositivoCreateDTO
from src.application.dtos.organizacion_dto import OrganizacionCreateDTO, PlantaCreateDTO
from src.application.dtos.purga_dto import PurgaRequestDTO
from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.application.use_cases.gestionar_dispositivos import GestionarDispositivosUseCase
from src.application.use_cases.ingestar_telemetria import IngestarTelemetriaUseCase
from src.application.use_cases.purgar_telemetria import PurgarTelemetriaExpiradaUseCase
from src.domain.telemetria.entities import (
    AcumuladoEnergia,
    AlertaDispositivo,
    Dispositivo,
    LecturaInstantanea,
    LogEstadoDispositivo,
    MedicionFase,
    Organizacion,
    Planta,
    PlanTelemetria,
)
from src.domain.telemetria.exceptions import LimiteDispositivosExcedidoError
from src.domain.telemetria.ports import (
    PublicadorEventosPort,
    RepositorioDispositivosPort,
    RepositorioOrganizacionesPort,
    RepositorioPlanesPort,
    RepositorioTelemetriaPort,
)
from src.domain.telemetria.value_objects import (
    MacAddress,
    SeveridadAlerta,
    VisibilidadPlan,
)


class MockEventPublisher(PublicadorEventosPort):
    def __init__(self):
        self.published = []

    def publicar_telemetria_en_vivo(self, topico: str, datos: dict) -> None:
        self.published.append((topico, datos))


class MockPlanesRepo(RepositorioPlanesPort):
    def __init__(self):
        self.planes: dict[str, PlanTelemetria] = {}

    def listar_planes(self) -> list[PlanTelemetria]:
        return list(self.planes.values())

    def obtener_por_id(self, plan_id: str) -> PlanTelemetria | None:
        return self.planes.get(plan_id)

    def guardar_plan(self, plan: PlanTelemetria) -> PlanTelemetria:
        self.planes[plan.id] = plan
        return plan


class MockOrganizacionesRepo(RepositorioOrganizacionesPort):
    def __init__(self):
        self.organizaciones: dict[str, Organizacion] = {}
        self.plantas: dict[str, Planta] = {}

    def obtener_por_id(self, organizacion_id: str) -> Organizacion | None:
        return self.organizaciones.get(organizacion_id)

    def listar_organizaciones(self) -> list[Organizacion]:
        return list(self.organizaciones.values())

    def guardar_organizacion(self, org: Organizacion) -> Organizacion:
        self.organizaciones[org.id] = org
        return org

    def obtener_planta_por_id(self, planta_id: str) -> Planta | None:
        return self.plantas.get(planta_id)

    def listar_plantas(self, organizacion_id: str | None = None) -> list[Planta]:
        if organizacion_id:
            return [p for p in self.plantas.values() if p.organizacion_id == organizacion_id]
        return list(self.plantas.values())

    def guardar_planta(self, planta: Planta) -> Planta:
        self.plantas[planta.id] = planta
        return planta


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
        if planta_id:
            return [d for d in self.dispositivos.values() if d.planta_id == planta_id]
        return list(self.dispositivos.values())

    def contar_por_organizacion(self, organizacion_id: str) -> int:
        return len([d for d in self.dispositivos.values() if d.planta_id])

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
        if alerta.id is not None:
            for idx, existing in enumerate(self.alertas):
                if existing.id == alerta.id:
                    self.alertas[idx] = alerta
                    return
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
        self, dispositivo_id: str, limite: int, desde: datetime | None = None
    ) -> list[LecturaInstantanea]:
        q = [i for i in self.instantaneas if i.dispositivo_id == dispositivo_id]
        if desde:
            q = [i for i in q if i.registrado_en >= desde]
        return q[:limite]

    def listar_energias(
        self, dispositivo_id: str, limite: int, desde: datetime | None = None
    ) -> list[AcumuladoEnergia]:
        q = [e for e in self.energias if e.dispositivo_id == dispositivo_id]
        if desde:
            q = [e for e in q if e.registrado_en >= desde]
        return q[:limite]

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


def test_downsampling_ingesta_5min():
    # Limpiar estado estático entre tests
    IngestarTelemetriaUseCase._ultimas_persistencias.clear()

    repo_disp = MockDispositivosRepo()
    repo_telem = MockTelemetriaRepo()
    pub = MockEventPublisher()

    use_case = IngestarTelemetriaUseCase(repo_disp, repo_telem, publicador=pub, granularidad_segundos=300)

    t0 = datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Enviar 5 mensajes seguidos (a 1s, 2s, 3s, 4s, 5s de diferencia)
    for i in range(5):
        payload = {
            "timestamp": (t0 + timedelta(seconds=i)).isoformat(),
            "phase_r": {"voltage_V": 220.0, "current_A": 1.0, "net_active_power_W": 220.0},
            "phase_s": {"voltage_V": 220.0, "current_A": 1.0, "net_active_power_W": 220.0},
            "phase_t": {"voltage_V": 220.0, "current_A": 1.0, "net_active_power_W": 220.0},
        }
        use_case.ejecutar("m/wifi/AABBCCDDEEFF/inst", payload)

    # WebSockets debe haber publicado los 5 paquetes en vivo
    assert len(pub.published) == 5
    # Pero en base de datos solo debe haberse persistido 1 fila gracias al downsampling de 5 min
    assert len(repo_telem.instantaneas) == 1

    # 2. Enviar un mensaje luego de transcurridos 301 segundos
    payload_futuro = {
        "timestamp": (t0 + timedelta(seconds=305)).isoformat(),
        "phase_r": {"voltage_V": 222.0, "current_A": 1.0, "net_active_power_W": 222.0},
    }
    use_case.ejecutar("m/wifi/AABBCCDDEEFF/inst", payload_futuro)

    # Ahora sí debe haberse persistido la segunda fila
    assert len(repo_telem.instantaneas) == 2


def test_evaluacion_alerta_a_pesar_de_downsampling():
    IngestarTelemetriaUseCase._ultimas_persistencias.clear()
    IngestarTelemetriaUseCase._device_cache.clear()
    IngestarTelemetriaUseCase._filtro_persistencia.limpiar()

    repo_disp = MockDispositivosRepo()
    repo_telem = MockTelemetriaRepo()
    use_case = IngestarTelemetriaUseCase(repo_disp, repo_telem, granularidad_segundos=300)

    t0 = datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone.utc)

    # Primer mensaje normal (se persiste)
    use_case.ejecutar(
        "m/wifi/AABBCCDDEEFF/inst",
        {"timestamp": t0.isoformat(), "phase_r": {"voltage_V": 220.0}},
    )
    assert len(repo_telem.instantaneas) == 1
    assert len(repo_telem.alertas) == 0

    # Segundo mensaje a los 10 segundos con baja tensión (180V) - 1ra lectura de anomalía
    use_case.ejecutar(
        "m/wifi/AABBCCDDEEFF/inst",
        {"timestamp": (t0 + timedelta(seconds=10)).isoformat(), "phase_r": {"voltage_V": 180.0}},
    )
    # Tercer mensaje a los 11 segundos con baja tensión (180V) - 2da lectura confirma persistencia
    use_case.ejecutar(
        "m/wifi/AABBCCDDEEFF/inst",
        {"timestamp": (t0 + timedelta(seconds=11)).isoformat(), "phase_r": {"voltage_V": 180.0}},
    )
    # No se persiste en instantáneas por downsampling
    assert len(repo_telem.instantaneas) == 1
    # Pero la alerta crítica se detecta y persiste tras confirmar persistencia temporal
    assert len(repo_telem.alertas) == 1
    assert repo_telem.alertas[0].tipo_alerta == "BAJA_TENSION"


def test_validacion_cupo_max_dispositivos():
    repo_disp = MockDispositivosRepo()
    repo_org = MockOrganizacionesRepo()
    repo_planes = MockPlanesRepo()

    plan1 = PlanTelemetria(
        id="plan-1",
        nombre="Plan Freemium 1 Dev",
        descripcion="Free",
        precio_mensual_ars=Decimal("0"),
        visibilidad=VisibilidadPlan.PUBLICO,
        retencion_dias=7,
        granularidad_minutos=5,
        max_dispositivos=1,
        canales_notificacion=[],
    )
    repo_planes.guardar_plan(plan1)

    use_case = GestionarDispositivosUseCase(repo_disp, repo_org, repo_planes)

    # Crear organización con Plan 1 (max 1 dispositivo)
    org_dto = use_case.crear_organizacion(OrganizacionCreateDTO(nombre="Empresa Test", plan_id="plan-1"))
    planta_dto = use_case.crear_planta(PlantaCreateDTO(organizacion_id=org_dto.id, nombre="Planta Central"))

    # 1. Registrar primer dispositivo (debe tener éxito)
    dev1 = use_case.registrar_dispositivo(
        DispositivoCreateDTO(device_uid="AABBCCDDEE01", nombre="Medidor 1", planta_id=planta_dto.id)
    )
    assert dev1.id is not None

    # 2. Intentar registrar segundo dispositivo para la misma organización (debe fallar)
    with pytest.raises(LimiteDispositivosExcedidoError):
        use_case.registrar_dispositivo(
            DispositivoCreateDTO(device_uid="AABBCCDDEE02", nombre="Medidor 2", planta_id=planta_dto.id)
        )


def test_purgar_telemetria_expirada():
    repo_telem = MockTelemetriaRepo()
    use_case = PurgarTelemetriaExpiradaUseCase(repo_telem)

    ahora = datetime.now(timezone.utc)
    antiguo = ahora - timedelta(days=15)
    reciente = ahora - timedelta(days=2)

    # Agregar instantáneas: 2 viejas (>7d), 1 reciente
    repo_telem.guardar_instantanea(
        LecturaInstantanea(None, "dev1", antiguo, MedicionFase(), MedicionFase(), MedicionFase())
    )
    repo_telem.guardar_instantanea(
        LecturaInstantanea(None, "dev1", antiguo + timedelta(hours=1), MedicionFase(), MedicionFase(), MedicionFase())
    )
    repo_telem.guardar_instantanea(
        LecturaInstantanea(None, "dev1", reciente, MedicionFase(), MedicionFase(), MedicionFase())
    )

    # Agregar alertas: 1 resuelta antigua (>30d), 1 no resuelta antigua (>30d), 1 reciente
    alerta_resuelta_vieja = AlertaDispositivo(
        None,
        "dev1",
        "BAJA_TENSION",
        SeveridadAlerta.WARNING,
        "Msg",
        esta_resuelta=True,
        disparada_en=antiguo,
        resuelta_en=antiguo,
    )
    alerta_activa_vieja = AlertaDispositivo(
        None,
        "dev1",
        "SOBRETENSION",
        SeveridadAlerta.CRITICAL,
        "Alerta abierta",
        esta_resuelta=False,
        disparada_en=antiguo,
    )
    repo_telem.guardar_alerta(alerta_resuelta_vieja)
    repo_telem.guardar_alerta(alerta_activa_vieja)

    # Ejecutar purga por defecto (7 días telemetría, 30 días alertas resueltas)
    req = PurgaRequestDTO(batch_size=100)
    res = use_case.ejecutar(req)

    assert res.instantaneas_eliminadas == 2
    assert len(repo_telem.instantaneas) == 1
    assert repo_telem.instantaneas[0].registrado_en == reciente

    # La alerta activa NO se debe borrar a pesar de ser antigua
    assert any(a.esta_resuelta is False for a in repo_telem.alertas)


def test_ventana_retencion_consultas():
    repo_disp = MockDispositivosRepo()
    repo_telem = MockTelemetriaRepo()
    repo_org = MockOrganizacionesRepo()
    repo_planes = MockPlanesRepo()

    plan_7d = PlanTelemetria(
        id="plan-7d",
        nombre="Plan Free 7d",
        descripcion="7 dias",
        precio_mensual_ars=Decimal("0"),
        visibilidad=VisibilidadPlan.PUBLICO,
        retencion_dias=7,
        granularidad_minutos=5,
        max_dispositivos=1,
        canales_notificacion=[],
    )
    repo_planes.guardar_plan(plan_7d)

    org = repo_org.guardar_organizacion(Organizacion(id="org-1", nombre="Org Test", plan_id="plan-7d"))
    planta = repo_org.guardar_planta(Planta(id="plant-1", organizacion_id=org.id, nombre="Planta 1"))
    dev = repo_disp.guardar(
        Dispositivo(id="dev-1", device_uid=MacAddress("AABBCCDDEE99"), nombre="PM 1", planta_id=planta.id)
    )

    ahora = datetime.now(timezone.utc)
    # Lectura de hace 15 días (fuera de la ventana)
    repo_telem.guardar_instantanea(
        LecturaInstantanea(None, dev.id, ahora - timedelta(days=15), MedicionFase(), MedicionFase(), MedicionFase())
    )
    # Lectura de hace 3 días (dentro de la ventana)
    repo_telem.guardar_instantanea(
        LecturaInstantanea(None, dev.id, ahora - timedelta(days=3), MedicionFase(), MedicionFase(), MedicionFase())
    )

    consultar_uc = ConsultarTelemetriaUseCase(repo_telem, repo_disp, repo_org, repo_planes)

    # Si se pide desde hace 30 días, la consulta debe quedar acotada a los 7 días de retención del plan
    resultado = consultar_uc.listar_instantaneas(dev.id, limite=100, desde=ahora - timedelta(days=30))
    assert len(resultado) == 1
    assert resultado[0].dispositivo_id == dev.id


def test_indices_modelos_sin_duplicados_redundantes():
    from src.infrastructure.sqlalchemy.models import (
        DeviceStatusLogModel,
        TelemetryEnergyModel,
        TelemetryInstantaneousModel,
    )

    for model in (TelemetryInstantaneousModel, TelemetryEnergyModel, DeviceStatusLogModel):
        # Verificar que device_id y recorded_at no tengan index=True propio duplicado
        col_device_id = model.__table__.columns["device_id"]
        col_recorded_at = model.__table__.columns["recorded_at"]
        assert col_device_id.index is not True, f"{model.__name__}.device_id tiene index=True redundante"
        assert col_recorded_at.index is not True, f"{model.__name__}.recorded_at tiene index=True redundante"


def test_device_cache_resolucion_en_memoria():
    # Limpiar estado estático
    IngestarTelemetriaUseCase._ultimas_persistencias.clear()
    IngestarTelemetriaUseCase._device_cache.clear()
    IngestarTelemetriaUseCase._ultimos_heartbeats.clear()

    class SpyDispositivosRepo(MockDispositivosRepo):
        def __init__(self):
            super().__init__()
            self.obtener_por_uid_calls = 0

        def obtener_por_uid(self, uid: MacAddress) -> Dispositivo | None:
            self.obtener_por_uid_calls += 1
            return super().obtener_por_uid(uid)

    repo_disp = SpyDispositivosRepo()
    repo_telem = MockTelemetriaRepo()
    use_case = IngestarTelemetriaUseCase(repo_disp, repo_telem)

    t0 = datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Primer mensaje: debe registrar el dispositivo y consultar DB
    use_case.ejecutar(
        "m/wifi/112233445566/inst",
        {"timestamp": t0.isoformat(), "phase_r": {"voltage_V": 220.0}},
    )
    assert repo_disp.obtener_por_uid_calls == 1

    # 2. Siguientes 5 mensajes del mismo dispositivo: deben resolverse por caché sin llamar a obtener_por_uid
    for i in range(1, 6):
        use_case.ejecutar(
            "m/wifi/112233445566/inst",
            {"timestamp": (t0 + timedelta(seconds=i)).isoformat(), "phase_r": {"voltage_V": 220.0}},
        )

    # La cuenta de llamadas a la base de datos debe seguir siendo 1 gracias a _device_cache
    assert repo_disp.obtener_por_uid_calls == 1


def test_heartbeat_throttling_60s():
    # Limpiar estado estático
    IngestarTelemetriaUseCase._ultimas_persistencias.clear()
    IngestarTelemetriaUseCase._device_cache.clear()
    IngestarTelemetriaUseCase._ultimos_heartbeats.clear()

    class SpyDispositivosRepo(MockDispositivosRepo):
        def __init__(self):
            super().__init__()
            self.guardar_calls = 0

        def guardar(self, dispositivo: Dispositivo) -> Dispositivo:
            self.guardar_calls += 1
            return super().guardar(dispositivo)

    repo_disp = SpyDispositivosRepo()
    repo_telem = MockTelemetriaRepo()
    use_case = IngestarTelemetriaUseCase(repo_disp, repo_telem)

    t0 = datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Primer mensaje (crea el dispositivo en DB)
    use_case.ejecutar(
        "m/wifi/AABB11223344/inst",
        {"timestamp": t0.isoformat(), "phase_r": {"voltage_V": 220.0}},
    )
    assert repo_disp.guardar_calls == 1

    # 2. Enviar 10 mensajes seguidos en los primeros 30 segundos
    for i in range(1, 11):
        use_case.ejecutar(
            "m/wifi/AABB11223344/inst",
            {"timestamp": (t0 + timedelta(seconds=i * 2)).isoformat(), "phase_r": {"voltage_V": 220.0}},
        )

    # El guardado en la tabla devices NO debe repetirse en cada frame (se mantiene en 1)
    assert repo_disp.guardar_calls == 1

    # 3. Enviar un mensaje luego de 65 segundos (ventana vencida)
    use_case.ejecutar(
        "m/wifi/AABB11223344/inst",
        {"timestamp": (t0 + timedelta(seconds=65)).isoformat(), "phase_r": {"voltage_V": 220.0}},
    )

    # Ahora sí debe haberse actualizado el heartbeat en DB
    assert repo_disp.guardar_calls == 2
