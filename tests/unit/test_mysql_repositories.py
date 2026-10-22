"""tests/unit/test_mysql_repositories.py — Pruebas de los repositorios SQLAlchemy con SQLite en memoria."""

from collections.abc import Iterator
from datetime import datetime, timezone
from decimal import Decimal
from itertools import count

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from src.domain.disponibilidad.entities import EventoDisponibilidad, Maquina, ParadaProgramada
from src.domain.disponibilidad.value_objects import EstadoMaquina, OrigenClasificacion, TipoParada
from src.domain.telemetria.entities import (
    AcumuladoEnergia,
    AlertaDispositivo,
    Dispositivo,
    LecturaInstantanea,
    LogEstadoDispositivo,
    MedicionFase,
    PlanTelemetria,
)
from src.domain.telemetria.value_objects import (
    Corriente,
    EnergiaActiva,
    EnergiaReactiva,
    EstadoDispositivo,
    FactorPotencia,
    MacAddress,
    PotenciaActiva,
    PotenciaAparente,
    PotenciaReactiva,
    SeveridadAlerta,
    Tension,
    VisibilidadPlan,
)
from src.infrastructure.sqlalchemy.models import (
    Base,
    DeviceAlertModel,
    DeviceModel,
    DeviceStatusLogModel,
    FacilityModel,
    MachineAvailabilityEventModel,
    PlanModel,
    TelemetryEnergyModel,
    TelemetryInstantaneousModel,
)
from src.infrastructure.sqlalchemy.mysql_repositories import (
    MySQLDispositivosRepository,
    MySQLEventosDisponibilidadRepository,
    MySQLMaquinasRepository,
    MySQLParadasProgramadasRepository,
    MySQLPlanesRepository,
    MySQLTelemetriaRepository,
)

_MODELOS_PK_AUTO = (
    TelemetryInstantaneousModel,
    TelemetryEnergyModel,
    DeviceStatusLogModel,
    DeviceAlertModel,
    MachineAvailabilityEventModel,
)

_contadores: dict[type, Iterator[int]] = {}


def _siguiente_id(clase: type) -> int:
    if clase not in _contadores:
        _contadores[clase] = count(1)
    return next(_contadores[clase])


def _asignar_pk_auto(session: Session, flush_context, instances) -> None:
    for obj in session.new:
        if isinstance(obj, _MODELOS_PK_AUTO) and obj.id is None:
            obj.id = _siguiente_id(obj.__class__)


@pytest.fixture()
def db() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine)
    session = session_local()
    event.listen(session, "before_flush", _asignar_pk_auto)
    try:
        yield session
    finally:
        session.close()


def _fecha(dia: int = 1, hora: int = 0) -> datetime:
    return datetime(2026, 1, dia, hora, 0, 0, tzinfo=timezone.utc)


def _fase(
    tension: float | None = 220.0,
    corriente: float | None = 1.0,
    activa: float | None = 220.0,
    reactiva: float | None = 10.0,
    aparente: float | None = 220.0,
    fp: float | None = 0.95,
) -> MedicionFase:
    return MedicionFase(
        tension=Tension(voltios=tension) if tension is not None else None,
        corriente=Corriente(amperios=corriente) if corriente is not None else None,
        potencia_activa=PotenciaActiva(vatios=activa) if activa is not None else None,
        potencia_reactiva=PotenciaReactiva(var=reactiva) if reactiva is not None else None,
        potencia_aparente=PotenciaAparente(va=aparente) if aparente is not None else None,
        factor_potencia=FactorPotencia(valor=fp) if fp is not None else None,
    )


def _dispositivo(uid: str = "AA:BB:CC:DD:EE:FF", planta_id: str | None = None) -> Dispositivo:
    return Dispositivo(
        id="dev-1",
        device_uid=MacAddress(uid),
        nombre="Powermeter 1",
        planta_id=planta_id,
    )


def test_dispositivo_guardar_y_obtener_por_id(db: Session) -> None:
    repo = MySQLDispositivosRepository(db)
    guardado = repo.guardar(_dispositivo())

    obtenido = repo.obtener_por_id("dev-1")

    assert guardado.id == "dev-1"
    assert obtenido is not None
    assert obtenido.device_uid.formateada() == "AA:BB:CC:DD:EE:FF"
    assert obtenido.nombre == "Powermeter 1"
    assert obtenido.estado == EstadoDispositivo.OFFLINE
    assert repo.obtener_por_id("inexistente") is None


def test_dispositivo_obtener_por_uid(db: Session) -> None:
    repo = MySQLDispositivosRepository(db)
    repo.guardar(_dispositivo())

    obtenido = repo.obtener_por_uid(MacAddress("AA-BB-CC-DD-EE-FF"))

    assert obtenido is not None
    assert obtenido.id == "dev-1"
    assert repo.obtener_por_uid(MacAddress("00:00:00:00:00:00")) is None


def test_dispositivo_guardar_actualiza_existente(db: Session) -> None:
    repo = MySQLDispositivosRepository(db)
    repo.guardar(_dispositivo())

    actualizado = _dispositivo()
    actualizado.nombre = "Renombrado"
    actualizado.esta_activo = False
    repo.guardar(actualizado)

    obtenido = repo.obtener_por_id("dev-1")
    assert obtenido is not None
    assert obtenido.nombre == "Renombrado"
    assert obtenido.esta_activo is False


def test_dispositivo_listar_con_y_sin_filtro(db: Session) -> None:
    repo = MySQLDispositivosRepository(db)
    repo.guardar(_dispositivo())
    otro = _dispositivo(uid="00:11:22:33:44:55", planta_id="plant-1")
    otro.id = "dev-2"
    repo.guardar(otro)

    todos = repo.listar()
    filtrados = repo.listar(planta_id="plant-1")

    assert len(todos) == 2
    assert len(filtrados) == 1
    assert filtrados[0].id == "dev-2"


def test_dispositivo_contar_por_organizacion(db: Session) -> None:
    db.add(FacilityModel(id="plant-1", organization_id="org-1", name="Planta 1"))
    db.commit()

    repo = MySQLDispositivosRepository(db)
    repo.guardar(_dispositivo(planta_id="plant-1"))

    assert repo.contar_por_organizacion("org-1") == 1
    assert repo.contar_por_organizacion("org-otra") == 0


def test_dispositivo_estado_invalido_fallback_offline(db: Session) -> None:
    db.add(
        DeviceModel(
            id="dev-x",
            device_uid="AABBCCDDEE00",
            name="x",
            estado="INVALIDO",
        )
    )
    db.commit()

    repo = MySQLDispositivosRepository(db)
    obtenido = repo.obtener_por_id("dev-x")

    assert obtenido is not None
    assert obtenido.estado == EstadoDispositivo.OFFLINE


def test_instantanea_guardar_y_obtener_ultima(db: Session) -> None:
    repo = MySQLTelemetriaRepository(db)
    lectura = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-1",
        registrado_en=_fecha(1, 10),
        fase_r=_fase(),
        fase_s=_fase(tension=219.0, corriente=None, activa=None, reactiva=None, aparente=None, fp=None),
        fase_t=_fase(tension=None, corriente=None, activa=None, reactiva=None, aparente=None, fp=None),
        potencia_activa_total=PotenciaActiva(vatios=220.0),
        desbalance_tension_porcentaje=3.45,
        voltage_linea_V=380.5,
        tension_neutro_estimada=2.34,
    )
    repo.guardar_instantanea(lectura)

    ultima = repo.obtener_ultima_instantanea("dev-1")

    assert ultima is not None
    assert ultima.fase_r.tension is not None
    assert ultima.fase_r.tension.voltios == 220.0
    assert ultima.fase_s.tension is not None
    assert ultima.fase_s.corriente is None
    assert ultima.fase_t.tension is None
    assert ultima.potencia_activa_total is not None
    assert ultima.potencia_activa_total.vatios == 220.0
    assert ultima.potencia_reactiva_total is None
    assert ultima.desbalance_tension_porcentaje == 3.45
    assert ultima.voltage_linea_V == 380.5
    assert ultima.tension_neutro_estimada == 2.34
    assert repo.obtener_ultima_instantanea("otro") is None


def test_instantanea_listar_con_desde_y_limite(db: Session) -> None:
    repo = MySQLTelemetriaRepository(db)
    for dia, hora in [(1, 8), (2, 8), (3, 8)]:
        repo.guardar_instantanea(
            LecturaInstantanea(
                id=None,
                dispositivo_id="dev-1",
                registrado_en=_fecha(dia, hora),
                fase_r=_fase(),
                fase_s=_fase(),
                fase_t=_fase(),
            )
        )

    todas = repo.listar_instantaneas("dev-1", limite=10)
    desde = repo.listar_instantaneas("dev-1", limite=10, desde=_fecha(2, 0))
    limitadas = repo.listar_instantaneas("dev-1", limite=1)

    assert len(todas) == 3
    assert len(desde) == 2
    assert len(limitadas) == 1


def test_energia_guardar_y_obtener_ultima(db: Session) -> None:
    repo = MySQLTelemetriaRepository(db)
    repo.guardar_energia(
        AcumuladoEnergia(
            id=None,
            dispositivo_id="dev-1",
            registrado_en=_fecha(1, 10),
            energia_activa_neta=EnergiaActiva(kwh=1.5),
            energia_reactiva_neta=EnergiaReactiva(kvarh=0.5),
            energia_activa_importada=EnergiaActiva(kwh=2.0),
        )
    )

    ultimo = repo.obtener_ultimo_acumulado("dev-1")

    assert ultimo is not None
    assert ultimo.energia_activa_neta is not None
    assert ultimo.energia_activa_neta.kwh == 1.5
    assert ultimo.energia_reactiva_neta is not None
    assert ultimo.energia_activa_exportada is None
    assert repo.obtener_ultimo_acumulado("otro") is None


def test_energia_listar_con_desde(db: Session) -> None:
    repo = MySQLTelemetriaRepository(db)
    for dia in (1, 2):
        repo.guardar_energia(
            AcumuladoEnergia(
                id=None,
                dispositivo_id="dev-1",
                registrado_en=_fecha(dia, 8),
                energia_activa_neta=EnergiaActiva(kwh=float(dia)),
            )
        )

    todas = repo.listar_energias("dev-1", limite=10)
    desde = repo.listar_energias("dev-1", limite=10, desde=_fecha(2, 0))

    assert len(todas) == 2
    assert len(desde) == 1


def test_log_estado_guardar(db: Session) -> None:
    repo = MySQLTelemetriaRepository(db)
    repo.guardar_log_estado(
        LogEstadoDispositivo(
            id=None,
            dispositivo_id="dev-1",
            registrado_en=_fecha(1, 10),
            wifi_rssi_dbm=-50,
            wifi_calidad=3,
            direccion_ip="192.168.1.10",
            tiempo_activo_segundos=3600,
            payload_bruto={"key": "value"},
        )
    )

    assert db.query(DeviceStatusLogModel).count() == 1


class _FakeAlertModel:
    def __init__(self) -> None:
        self.id = 1
        self.device_id = "dev-1"
        self.alert_type = "X"
        self.severity = "INVALIDO"
        self.message = "m"
        self.is_resolved = False
        self.triggered_at = _fecha(1, 10)
        self.resolved_at = None
        self.phase = "R"
        self.measured_value = None
        self.threshold_value = None
        self.unit = "V"
        self.category = "TENSION"
        self.notes = None
        self.last_detected_at = None
        self.occurrences = 1


def test_alerta_guardar_nueva_asigna_id(db: Session) -> None:
    repo = MySQLTelemetriaRepository(db)
    alerta = AlertaDispositivo(
        id=None,
        dispositivo_id="dev-1",
        tipo_alerta="BAJA_TENSION",
        severidad=SeveridadAlerta.WARNING,
        mensaje="Tension baja",
    )

    repo.guardar_alerta(alerta)

    assert alerta.id is not None


def test_alerta_guardar_existente_actualiza(db: Session) -> None:
    repo = MySQLTelemetriaRepository(db)
    alerta = AlertaDispositivo(
        id=None,
        dispositivo_id="dev-1",
        tipo_alerta="BAJA_TENSION",
        severidad=SeveridadAlerta.WARNING,
        mensaje="original",
    )
    repo.guardar_alerta(alerta)
    alerta.mensaje = "actualizado"
    alerta.esta_resuelta = True
    repo.guardar_alerta(alerta)

    obtenida = repo.obtener_alerta_por_id(alerta.id)

    assert obtenida is not None
    assert obtenida.mensaje == "actualizado"
    assert obtenida.esta_resuelta is True
    assert repo.obtener_alerta_por_id(999999) is None


def test_alerta_listar_filtros(db: Session) -> None:
    repo = MySQLTelemetriaRepository(db)
    repo.guardar_alerta(
        AlertaDispositivo(
            id=None, dispositivo_id="dev-1", tipo_alerta="A", severidad=SeveridadAlerta.INFO, mensaje="m1"
        )
    )
    repo.guardar_alerta(
        AlertaDispositivo(
            id=None,
            dispositivo_id="dev-1",
            tipo_alerta="B",
            severidad=SeveridadAlerta.CRITICAL,
            mensaje="m2",
            esta_resuelta=True,
        )
    )
    repo.guardar_alerta(
        AlertaDispositivo(
            id=None, dispositivo_id="dev-2", tipo_alerta="C", severidad=SeveridadAlerta.INFO, mensaje="m3"
        )
    )

    assert len(repo.listar_alertas()) == 3
    assert len(repo.listar_alertas(dispositivo_id="dev-1")) == 2
    assert len(repo.listar_alertas(solo_abiertas=True)) == 2
    assert len(repo.listar_alertas(limite=1)) == 1


def test_alerta_severidad_invalida_fallback(db: Session) -> None:
    repo = MySQLTelemetriaRepository(db)

    entidad = repo._alerta_to_entity(_FakeAlertModel())

    assert entidad.severidad == SeveridadAlerta.WARNING


def test_purgar_instantaneas(db: Session) -> None:
    repo = MySQLTelemetriaRepository(db)
    for dia in (1, 2):
        repo.guardar_instantanea(
            LecturaInstantanea(
                id=None,
                dispositivo_id="dev-1",
                registrado_en=_fecha(dia, 8),
                fase_r=_fase(),
                fase_s=_fase(),
                fase_t=_fase(),
            )
        )

    purgadas = repo.purgar_instantaneas_anteriores_a(_fecha(2, 0))

    assert purgadas == 1
    assert len(repo.listar_instantaneas("dev-1", limite=10)) == 1


def test_purgar_energias(db: Session) -> None:
    repo = MySQLTelemetriaRepository(db)
    for dia in (1, 2):
        repo.guardar_energia(AcumuladoEnergia(id=None, dispositivo_id="dev-1", registrado_en=_fecha(dia, 8)))

    purgadas = repo.purgar_energias_anteriores_a(_fecha(2, 0))

    assert purgadas == 1
    assert len(repo.listar_energias("dev-1", limite=10)) == 1


def test_purgar_status_logs(db: Session) -> None:
    repo = MySQLTelemetriaRepository(db)
    for dia in (1, 2):
        repo.guardar_log_estado(LogEstadoDispositivo(id=None, dispositivo_id="dev-1", registrado_en=_fecha(dia, 8)))

    purgadas = repo.purgar_status_logs_anteriores_a(_fecha(2, 0))

    assert purgadas == 1


def test_purgar_alertas_resueltas(db: Session) -> None:
    repo = MySQLTelemetriaRepository(db)
    repo.guardar_alerta(
        AlertaDispositivo(
            id=None,
            dispositivo_id="dev-1",
            tipo_alerta="A",
            severidad=SeveridadAlerta.WARNING,
            mensaje="resuelta",
            esta_resuelta=True,
            resuelta_en=_fecha(1, 9),
        )
    )
    repo.guardar_alerta(
        AlertaDispositivo(
            id=None, dispositivo_id="dev-1", tipo_alerta="B", severidad=SeveridadAlerta.WARNING, mensaje="abierta"
        )
    )

    purgadas = repo.purgar_alertas_resueltas_anteriores_a(_fecha(3, 0))

    assert purgadas == 1


def test_purgar_sin_datos_devuelve_cero(db: Session) -> None:
    repo = MySQLTelemetriaRepository(db)

    assert repo.purgar_instantaneas_anteriores_a(_fecha(2, 0)) == 0
    assert repo.purgar_energias_anteriores_a(_fecha(2, 0)) == 0
    assert repo.purgar_status_logs_anteriores_a(_fecha(2, 0)) == 0
    assert repo.purgar_alertas_resueltas_anteriores_a(_fecha(2, 0)) == 0


def test_plan_guardar_y_obtener(db: Session) -> None:
    repo = MySQLPlanesRepository(db)
    repo.guardar_plan(
        PlanTelemetria(
            id="plan-1",
            nombre="Basico",
            descripcion="desc",
            precio_mensual_ars=Decimal("1000.00"),
            visibilidad=VisibilidadPlan.PUBLICO,
            retencion_dias=30,
            granularidad_minutos=1,
            max_dispositivos=10,
            canales_notificacion=["email"],
        )
    )

    obtenido = repo.obtener_por_id("plan-1")

    assert obtenido is not None
    assert obtenido.nombre == "Basico"
    assert obtenido.precio_mensual_ars == Decimal("1000.00")
    assert obtenido.canales_notificacion == ["email"]
    assert repo.obtener_por_id("inexistente") is None


def test_plan_guardar_actualiza(db: Session) -> None:
    repo = MySQLPlanesRepository(db)
    plan = PlanTelemetria(
        id="plan-1",
        nombre="Basico",
        descripcion="desc",
        precio_mensual_ars=Decimal("1000.00"),
        visibilidad=VisibilidadPlan.PUBLICO,
        retencion_dias=30,
        granularidad_minutos=1,
        max_dispositivos=10,
        canales_notificacion=["email"],
    )
    repo.guardar_plan(plan)
    plan.nombre = "Pro"
    plan.precio_mensual_ars = Decimal("5000.00")
    repo.guardar_plan(plan)

    obtenido = repo.obtener_por_id("plan-1")
    assert obtenido is not None
    assert obtenido.nombre == "Pro"
    assert obtenido.precio_mensual_ars == Decimal("5000.00")


def test_plan_listar(db: Session) -> None:
    repo = MySQLPlanesRepository(db)
    repo.guardar_plan(
        PlanTelemetria(
            id="plan-1",
            nombre="Basico",
            descripcion="desc",
            precio_mensual_ars=Decimal("1000.00"),
            visibilidad=VisibilidadPlan.PUBLICO,
            retencion_dias=30,
            granularidad_minutos=1,
            max_dispositivos=10,
            canales_notificacion=["email"],
        )
    )

    assert len(repo.listar_planes()) == 1


def test_plan_visibilidad_invalida_fallback(db: Session) -> None:
    db.add(
        PlanModel(
            id="plan-x",
            name="x",
            description="d",
            monthly_price_ars=Decimal("1.00"),
            visibility="INVALIDO",
            retention_days=1,
            granularity_minutes=1,
            max_devices=1,
            notification_channels=[],
        )
    )
    db.commit()

    repo = MySQLPlanesRepository(db)
    obtenido = repo.obtener_por_id("plan-x")

    assert obtenido is not None
    assert obtenido.visibilidad == VisibilidadPlan.PUBLICO


def test_maquina_guardar_y_obtener_por_id(db: Session) -> None:
    MySQLDispositivosRepository(db).guardar(_dispositivo())
    repo = MySQLMaquinasRepository(db)

    repo.guardar(Maquina(id="maq-1", dispositivo_id="dev-1", nombre="Línea 1"))

    obtenida = repo.obtener_por_id("maq-1")
    assert obtenida is not None
    assert obtenida.dispositivo_id == "dev-1"
    assert obtenida.umbral_marcha_w is None
    assert obtenida.esta_calibrada is False
    assert repo.obtener_por_dispositivo_id("dev-1") is not None
    assert repo.obtener_por_id("inexistente") is None


def test_maquina_guardar_actualiza_umbral(db: Session) -> None:
    MySQLDispositivosRepository(db).guardar(_dispositivo())
    repo = MySQLMaquinasRepository(db)
    maquina = repo.guardar(Maquina(id="maq-1", dispositivo_id="dev-1", nombre="Línea 1"))

    maquina.umbral_marcha_w = 1500.5
    repo.guardar(maquina)

    obtenida = repo.obtener_por_id("maq-1")
    assert obtenida is not None
    assert obtenida.umbral_marcha_w == 1500.5
    assert obtenida.esta_calibrada is True


def test_maquina_listar(db: Session) -> None:
    repo_disp = MySQLDispositivosRepository(db)
    repo_disp.guardar(_dispositivo())
    otro_disp = _dispositivo(uid="00:11:22:33:44:66")
    otro_disp.id = "dev-2"
    repo_disp.guardar(otro_disp)

    repo = MySQLMaquinasRepository(db)
    repo.guardar(Maquina(id="maq-1", dispositivo_id="dev-1", nombre="Línea 1"))
    repo.guardar(Maquina(id="maq-2", dispositivo_id="dev-2", nombre="Línea 2"))

    assert {m.id for m in repo.listar()} == {"maq-1", "maq-2"}


def test_evento_disponibilidad_guardar_y_obtener_abierto(db: Session) -> None:
    MySQLDispositivosRepository(db).guardar(_dispositivo())
    MySQLMaquinasRepository(db).guardar(Maquina(id="maq-1", dispositivo_id="dev-1", nombre="Línea 1"))
    repo = MySQLEventosDisponibilidadRepository(db)

    guardado = repo.guardar(
        EventoDisponibilidad(id=None, maquina_id="maq-1", estado=EstadoMaquina.MARCHA, inicio_at=_fecha(1, 8))
    )
    assert guardado.id is not None

    abierto = repo.obtener_evento_abierto("maq-1")
    assert abierto is not None
    assert abierto.estado == EstadoMaquina.MARCHA
    assert abierto.esta_abierto is True


def test_evento_disponibilidad_cerrar_y_correccion_manual(db: Session) -> None:
    MySQLDispositivosRepository(db).guardar(_dispositivo())
    MySQLMaquinasRepository(db).guardar(Maquina(id="maq-1", dispositivo_id="dev-1", nombre="Línea 1"))
    repo = MySQLEventosDisponibilidadRepository(db)

    evento = repo.guardar(
        EventoDisponibilidad(
            id=None,
            maquina_id="maq-1",
            estado=EstadoMaquina.PARADA,
            tipo_parada=TipoParada.SIN_CLASIFICAR,
            inicio_at=_fecha(1, 8),
        )
    )
    evento.cerrar(_fecha(1, 9), potencia_promedio_w=12.5)
    repo.guardar(evento)
    evento.marcar_correccion_manual(
        TipoParada.PROGRAMADA, usuario_id="user-1", comentario="mantenimiento", ahora=_fecha(1, 10)
    )
    repo.guardar(evento)

    recargado = repo.obtener_por_id(evento.id)
    assert recargado is not None
    assert recargado.fin_at == _fecha(1, 9)
    assert recargado.tipo_parada == TipoParada.PROGRAMADA
    assert recargado.origen == OrigenClasificacion.CORRECCION_HUMANA
    assert recargado.corregido_por_usuario_id == "user-1"
    assert recargado.esta_abierto is False
    assert repo.obtener_evento_abierto("maq-1") is None


def test_parada_programada_guardar_y_buscar_vigente(db: Session) -> None:
    MySQLDispositivosRepository(db).guardar(_dispositivo())
    MySQLMaquinasRepository(db).guardar(Maquina(id="maq-1", dispositivo_id="dev-1", nombre="Línea 1"))
    repo = MySQLParadasProgramadasRepository(db)

    repo.guardar(
        ParadaProgramada(
            id="parada-1",
            maquina_id="maq-1",
            inicio_at=_fecha(1, 8),
            fin_at=_fecha(1, 10),
            motivo="Mantenimiento programado",
        )
    )

    vigente = repo.buscar_vigente("maq-1", _fecha(1, 9))
    assert vigente is not None
    assert vigente.motivo == "Mantenimiento programado"
    assert repo.buscar_vigente("maq-1", _fecha(1, 11)) is None
    assert len(repo.listar_por_maquina("maq-1")) == 1
