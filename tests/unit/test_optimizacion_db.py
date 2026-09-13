"""tests/unit/test_optimizacion_db.py."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.application.dtos.dispositivo_dto import DispositivoCreateDTO
from src.application.dtos.purga_dto import PurgaRequestDTO
from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.application.use_cases.gestionar_dispositivos import GestionarDispositivosUseCase
from src.application.use_cases.ingestar_telemetria import IngestarTelemetriaUseCase
from src.application.use_cases.purgar_telemetria import PurgarTelemetriaExpiradaUseCase
from src.domain.telemetria.entities import (
    AcumuladoEnergia,
    AlertaDispositivo,
    Dispositivo,
    DispositivoLayout,
    LecturaInstantanea,
    LogEstadoDispositivo,
    MedicionFase,
    NodoUnifilar,
    Organizacion,
    Planta,
    PlanTelemetria,
    Suscripcion,
    ZonaPlanta,
)
from src.domain.telemetria.exceptions import LimiteDispositivosExcedidoError
from src.domain.telemetria.ports import (
    PublicadorEventosPort,
    RepositorioDispositivosPort,
    RepositorioOrganizacionesPort,
    RepositorioPlanesPort,
    RepositorioSuscripcionesPort,
    RepositorioTelemetriaPort,
)
from src.domain.telemetria.value_objects import (
    LecturaPotenciaTemporal,
    MacAddress,
    ModoFreeTier,
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

    def obtener_nodos_unifilar(self, planta_id: str) -> list[NodoUnifilar]:
        return []

    def guardar_nodos_unifilar(self, planta_id: str, nodos: list[NodoUnifilar]) -> list[NodoUnifilar]:
        return list(nodos)

    def obtener_zonas_planta(self, planta_id: str) -> list[ZonaPlanta]:
        return []

    def obtener_dispositivos_layout(self, planta_id: str) -> list[DispositivoLayout]:
        return []

    def guardar_layout_planta(
        self,
        planta_id: str,
        plano_svg_url: str | None,
        zonas: list[ZonaPlanta],
        dispositivos: list[DispositivoLayout],
    ) -> None:
        pass


class MockSuscripcionesRepo(RepositorioSuscripcionesPort):
    def __init__(self):
        self.suscripciones: dict[str, Suscripcion] = {}

    def obtener_por_organizacion(self, organizacion_id: str) -> Suscripcion | None:
        return self.suscripciones.get(organizacion_id)

    def guardar(self, suscripcion: Suscripcion) -> Suscripcion:
        self.suscripciones[suscripcion.organizacion_id] = suscripcion
        return suscripcion


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

    @staticmethod
    def _gte(a: datetime, b: datetime) -> bool:
        a_utc = a if a.tzinfo is not None else a.replace(tzinfo=timezone.utc)
        b_utc = b if b.tzinfo is not None else b.replace(tzinfo=timezone.utc)
        return a_utc >= b_utc

    def listar_instantaneas(
        self, dispositivo_id: str, limite: int, desde: datetime | None = None
    ) -> list[LecturaInstantanea]:
        q = [i for i in self.instantaneas if i.dispositivo_id == dispositivo_id]
        if desde:
            q = [i for i in q if self._gte(i.registrado_en, desde)]
        return q[:limite]

    def listar_energias(
        self, dispositivo_id: str, limite: int, desde: datetime | None = None
    ) -> list[AcumuladoEnergia]:
        q = [e for e in self.energias if e.dispositivo_id == dispositivo_id]
        if desde:
            q = [e for e in q if self._gte(e.registrado_en, desde)]
        return q[:limite]

    def listar_ultimos_acumulados_por_periodo(
        self, dispositivo_id: str, desde: datetime | None = None, granularidad: str = "day", zona: str = "UTC"
    ) -> list[AcumuladoEnergia]:
        q = [e for e in self.energias if e.dispositivo_id == dispositivo_id]
        if desde:
            q = [e for e in q if self._gte(e.registrado_en, desde)]
        return q

    def listar_potencias_para_histograma(
        self, dispositivo_id: str, desde: datetime, limite: int | None = None
    ) -> list[LecturaPotenciaTemporal]:
        items = [
            LecturaPotenciaTemporal(momento=i.registrado_en, potencia_w=i.potencia_activa_total.vatios)
            for i in self.instantaneas
            if i.dispositivo_id == dispositivo_id
            and i.potencia_activa_total is not None
            and self._gte(i.registrado_en, desde)
        ]
        items.sort(key=lambda x: x.momento)
        if limite is not None:
            items = items[:limite]
        return items

    def purgar_instantaneas_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        prev = len(self.instantaneas)
        self.instantaneas = [i for i in self.instantaneas if self._gte(i.registrado_en, fecha_limite)]
        return prev - len(self.instantaneas)

    def purgar_energias_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        prev = len(self.energias)
        self.energias = [e for e in self.energias if self._gte(e.registrado_en, fecha_limite)]
        return prev - len(self.energias)

    def purgar_status_logs_anteriores_a(self, fecha_limite: datetime, batch_size: int = 1000) -> int:
        prev = len(self.logs)
        self.logs = [log_item for log_item in self.logs if self._gte(log_item.registrado_en, fecha_limite)]
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

    repo_sus = MockSuscripcionesRepo()
    use_case = GestionarDispositivosUseCase(repo_disp, repo_org, repo_planes, repo_suscripciones=repo_sus)

    # Organización con Plan 1 (max 1 dispositivo): identidad en el repo YAML, plan en la suscripción
    repo_org.guardar_organizacion(Organizacion(id="org-test", nombre="Empresa Test"))
    repo_sus.guardar(Suscripcion(organizacion_id="org-test", plan_id="plan-1"))
    planta_dto = repo_org.guardar_planta(
        Planta(id="planta-central", organizacion_id="org-test", nombre="Planta Central")
    )

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

    org = repo_org.guardar_organizacion(Organizacion(id="org-1", nombre="Org Test"))
    repo_sus = MockSuscripcionesRepo()
    repo_sus.guardar(Suscripcion(organizacion_id="org-1", plan_id="plan-7d"))
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

    consultar_uc = ConsultarTelemetriaUseCase(repo_telem, repo_disp, repo_org, repo_planes, repo_suscripciones=repo_sus)

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
            self.actualizar_heartbeat_calls = 0

        def guardar(self, dispositivo: Dispositivo) -> Dispositivo:
            self.guardar_calls += 1
            return super().guardar(dispositivo)

        def actualizar_heartbeat(self, *args, **kwargs) -> None:
            self.actualizar_heartbeat_calls += 1
            return super().actualizar_heartbeat(*args, **kwargs)

    repo_disp = SpyDispositivosRepo()
    repo_telem = MockTelemetriaRepo()
    use_case = IngestarTelemetriaUseCase(repo_disp, repo_telem)

    t0 = datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Primer mensaje (crea el dispositivo en DB, vía guardar())
    use_case.ejecutar(
        "m/wifi/AABB11223344/inst",
        {"timestamp": t0.isoformat(), "phase_r": {"voltage_V": 220.0}},
    )
    assert repo_disp.guardar_calls == 1
    assert repo_disp.actualizar_heartbeat_calls == 0

    # 2. Enviar 10 mensajes seguidos en los primeros 30 segundos
    for i in range(1, 11):
        use_case.ejecutar(
            "m/wifi/AABB11223344/inst",
            {"timestamp": (t0 + timedelta(seconds=i * 2)).isoformat(), "phase_r": {"voltage_V": 220.0}},
        )

    # El guardado en la tabla devices NO debe repetirse en cada frame (se mantiene en 1)
    assert repo_disp.guardar_calls == 1
    assert repo_disp.actualizar_heartbeat_calls == 0

    # 3. Enviar un mensaje luego de 65 segundos (ventana vencida)
    use_case.ejecutar(
        "m/wifi/AABB11223344/inst",
        {"timestamp": (t0 + timedelta(seconds=65)).isoformat(), "phase_r": {"voltage_V": 220.0}},
    )

    # El refresco de heartbeat se persiste vía actualizar_heartbeat() (UPDATE parcial), no
    # guardar() -- así una reasignación de planta hecha por fuera no se pisa con el heartbeat.
    assert repo_disp.guardar_calls == 1
    assert repo_disp.actualizar_heartbeat_calls == 1


def test_consultar_telemetria_modo_pro_y_free_bifurcado():
    repo_telem = MockTelemetriaRepo()
    repo_disp = MockDispositivosRepo()
    repo_org = MockOrganizacionesRepo()
    repo_sus = MockSuscripcionesRepo()

    ahora = datetime.now(timezone.utc)

    # 1. Caso PRO: Organización con PRO activo vence en 40 días
    repo_org.guardar_organizacion(Organizacion(id="org-pro", nombre="Industria Pro Activa"))
    repo_sus.guardar(
        Suscripcion(
            organizacion_id="org-pro", pro_vence_en=ahora + timedelta(days=40), modo_free=ModoFreeTier.PRIVADO_BASICO
        )
    )
    planta_pro = Planta(id="planta-pro", organizacion_id="org-pro", nombre="Planta Central")
    repo_org.guardar_planta(planta_pro)
    dev_pro = Dispositivo(
        id="dev-pro", device_uid=MacAddress("AABBCCDDEE01"), nombre="Medidor Pro", planta_id="planta-pro"
    )
    repo_disp.guardar(dev_pro)

    # Ingestar lecturas
    repo_telem.guardar_instantanea(
        LecturaInstantanea(1, dev_pro.id, ahora - timedelta(minutes=5), MedicionFase(), MedicionFase(), MedicionFase())
    )
    repo_telem.guardar_instantanea(
        LecturaInstantanea(2, dev_pro.id, ahora - timedelta(days=100), MedicionFase(), MedicionFase(), MedicionFase())
    )

    consultar_uc = ConsultarTelemetriaUseCase(repo_telem, repo_disp, repo_org, repo_suscripciones=repo_sus)

    # PRO puede consultar raw sin restricción y retención hasta 365 días
    lecturas_pro = consultar_uc.listar_instantaneas(
        dev_pro.id, limite=100, desde=ahora - timedelta(days=200), granularidad="raw"
    )
    assert len(lecturas_pro) == 2

    # 2. Caso Free Privado Básico: PRO vencido hace 10 días
    repo_org.guardar_organizacion(Organizacion(id="org-free-priv", nombre="Industria Free Privada"))
    repo_sus.guardar(
        Suscripcion(
            organizacion_id="org-free-priv",
            pro_vence_en=ahora - timedelta(days=10),
            modo_free=ModoFreeTier.PRIVADO_BASICO,
        )
    )
    planta_free_priv = Planta(id="planta-free-priv", organizacion_id="org-free-priv", nombre="Planta Privada")
    repo_org.guardar_planta(planta_free_priv)
    dev_free_priv = Dispositivo(
        id="dev-free-priv",
        device_uid=MacAddress("AABBCCDDEE02"),
        nombre="Medidor Privado",
        planta_id="planta-free-priv",
    )
    repo_disp.guardar(dev_free_priv)

    repo_telem.guardar_instantanea(
        LecturaInstantanea(
            3, dev_free_priv.id, ahora - timedelta(minutes=10), MedicionFase(), MedicionFase(), MedicionFase()
        )
    )
    repo_telem.guardar_instantanea(
        LecturaInstantanea(
            4, dev_free_priv.id, ahora - timedelta(days=20), MedicionFase(), MedicionFase(), MedicionFase()
        )
    )

    # Privado Básico: la retención es de 14 días (la lectura de hace 20 días no entra) y fuerza agregación (mínimo 1 hora)
    lecturas_free_priv = consultar_uc.listar_instantaneas(
        dev_free_priv.id, limite=100, desde=ahora - timedelta(days=30), granularidad="raw"
    )
    assert len(lecturas_free_priv) == 1


def test_consultar_telemetria_con_fechas_naive_en_bd():
    from datetime import datetime, timezone

    repo_telem = MockTelemetriaRepo()
    repo_disp = MockDispositivosRepo()
    repo_org = MockOrganizacionesRepo()
    repo_sus = MockSuscripcionesRepo()

    # Fechas naive como las que devuelve MySQL / SQLite sin timezone
    venc_naive = datetime(2026, 12, 31, 23, 59, 59)
    ahora_naive = datetime(2026, 8, 23, 10, 0, 0)

    repo_org.guardar_organizacion(Organizacion(id="org-naive", nombre="Org Naive"))
    repo_sus.guardar(
        Suscripcion(organizacion_id="org-naive", pro_vence_en=venc_naive, modo_free=ModoFreeTier.PRIVADO_BASICO)
    )
    planta = Planta(id="planta-naive", organizacion_id="org-naive", nombre="Planta Naive")
    repo_org.guardar_planta(planta)
    dev = Dispositivo(
        id="dev-naive",
        device_uid=MacAddress("AABBCCDDEE99"),
        nombre="Medidor Naive",
        planta_id="planta-naive",
    )
    repo_disp.guardar(dev)

    repo_telem.guardar_instantanea(
        LecturaInstantanea(1, dev.id, ahora_naive, MedicionFase(), MedicionFase(), MedicionFase())
    )

    consultar_uc = ConsultarTelemetriaUseCase(repo_telem, repo_disp, repo_org, repo_suscripciones=repo_sus)

    # Llamada con hours=24 (genera 'desde' con timezone.utc)
    desde_aware = datetime.now(timezone.utc) - timedelta(hours=24)
    res = consultar_uc.listar_instantaneas(
        id_o_uid=dev.id,
        limite=100,
        desde=desde_aware,
        granularidad="auto",
        horas=24,
    )
    assert isinstance(res, list)

    # Llamada energy con days=7
    desde_energy_aware = datetime.now(timezone.utc) - timedelta(days=7)
    res_energy = consultar_uc.listar_energias(
        id_o_uid=dev.id,
        limite=100,
        desde=desde_energy_aware,
    )
    assert isinstance(res_energy, list)
