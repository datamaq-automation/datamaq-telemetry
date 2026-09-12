"""tests/unit/test_notificaciones_alertas_criticas.py."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from src.application.use_cases.ingesta.procesador_alertas_ingesta import (
    ProcesadorAlertasIngesta,
)
from src.domain.telemetria.entities import (
    AlertaDispositivo,
    Dispositivo,
    LecturaInstantanea,
    MedicionFase,
)
from src.domain.telemetria.ports import (
    NotificadorAlertasPort,
    PublicadorEventosPort,
    RepositorioTelemetriaPort,
)
from src.domain.telemetria.value_objects import (
    Corriente,
    FactorPotencia,
    MacAddress,
    PotenciaActiva,
    SeveridadAlerta,
    Tension,
)
from src.infrastructure.auth.email_service import (
    _construir_mensaje_alerta_critica,
)


@pytest.fixture(autouse=True)
def _limpiar_estado():
    ProcesadorAlertasIngesta._filtro_persistencia.limpiar()
    ProcesadorAlertasIngesta._cooldown_notificaciones.limpiar()
    ProcesadorAlertasIngesta.configurar_notificador(None, [])
    yield
    ProcesadorAlertasIngesta._filtro_persistencia.limpiar()
    ProcesadorAlertasIngesta._cooldown_notificaciones.limpiar()
    ProcesadorAlertasIngesta.configurar_notificador(None, [])


def _dispositivo() -> Dispositivo:
    return Dispositivo(
        id="dev-test-1",
        device_uid=MacAddress("AA:BB:CC:DD:EE:FF"),
        nombre="Compresor Central",
    )


def _lectura_falta_fase(t: datetime) -> LecturaInstantanea:
    fase_0v = MedicionFase(
        tension=Tension(0.0),
        corriente=Corriente(0.0),
        potencia_activa=PotenciaActiva(0.0),
        factor_potencia=FactorPotencia(1.0),
    )
    fase_ok = MedicionFase(
        tension=Tension(220.0),
        corriente=Corriente(10.0),
        potencia_activa=PotenciaActiva(2200.0),
        factor_potencia=FactorPotencia(0.95),
    )
    return LecturaInstantanea(
        id=None,
        dispositivo_id="dev-test-1",
        registrado_en=t,
        fase_r=fase_0v,
        fase_s=fase_ok,
        fase_t=fase_ok,
        potencia_activa_total=PotenciaActiva(4400.0),
    )


def test_alerta_critica_despacha_notificacion_email():
    mock_notif = MagicMock(spec=NotificadorAlertasPort)
    mock_repo = MagicMock(spec=RepositorioTelemetriaPort)
    mock_pub = MagicMock(spec=PublicadorEventosPort)

    ProcesadorAlertasIngesta.configurar_notificador(mock_notif, ["guardia@datamaq.com.ar"])
    disp = _dispositivo()

    t0 = datetime(2026, 9, 7, 10, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=4)

    lectura0 = _lectura_falta_fase(t0)
    ProcesadorAlertasIngesta.procesar_alertas(
        dispositivo=disp,
        mac_raw="AABBCCDDEEFF",
        lectura=lectura0,
        recorded_at=t0,
        repo_telemetria=mock_repo,
        publicador=mock_pub,
    )
    assert mock_notif.notificar_alerta_critica.call_count == 0

    lectura1 = _lectura_falta_fase(t1)
    ProcesadorAlertasIngesta.procesar_alertas(
        dispositivo=disp,
        mac_raw="AABBCCDDEEFF",
        lectura=lectura1,
        recorded_at=t1,
        repo_telemetria=mock_repo,
        publicador=mock_pub,
    )

    assert mock_notif.notificar_alerta_critica.call_count == 2
    alertas_despachadas = [call[0][0] for call in mock_notif.notificar_alerta_critica.call_args_list]
    tipos = {a.tipo_alerta for a in alertas_despachadas}
    assert "FALTA_FASE" in tipos
    assert "DESBALANCE_CORRIENTE_CRITICAL" in tipos
    for a in alertas_despachadas:
        assert a.severidad == SeveridadAlerta.CRITICAL


def test_alerta_critica_respeta_cooldown():
    mock_notif = MagicMock(spec=NotificadorAlertasPort)
    mock_repo = MagicMock(spec=RepositorioTelemetriaPort)

    ProcesadorAlertasIngesta.configurar_notificador(mock_notif, ["guardia@datamaq.com.ar"])
    disp = _dispositivo()

    t0 = datetime(2026, 9, 7, 10, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=4)
    t2 = t0 + timedelta(seconds=60)

    ProcesadorAlertasIngesta.procesar_alertas(
        dispositivo=disp,
        mac_raw="AABBCCDDEEFF",
        lectura=_lectura_falta_fase(t0),
        recorded_at=t0,
        repo_telemetria=mock_repo,
    )
    ProcesadorAlertasIngesta.procesar_alertas(
        dispositivo=disp,
        mac_raw="AABBCCDDEEFF",
        lectura=_lectura_falta_fase(t1),
        recorded_at=t1,
        repo_telemetria=mock_repo,
    )
    assert mock_notif.notificar_alerta_critica.call_count == 2

    ProcesadorAlertasIngesta.procesar_alertas(
        dispositivo=disp,
        mac_raw="AABBCCDDEEFF",
        lectura=_lectura_falta_fase(t2),
        recorded_at=t2,
        repo_telemetria=mock_repo,
    )
    assert mock_notif.notificar_alerta_critica.call_count == 2


def test_alerta_warning_no_despacha_email():
    mock_notif = MagicMock(spec=NotificadorAlertasPort)
    mock_repo = MagicMock(spec=RepositorioTelemetriaPort)

    ProcesadorAlertasIngesta.configurar_notificador(mock_notif, ["guardia@datamaq.com.ar"])
    disp = _dispositivo()

    fase_ok = MedicionFase(
        tension=Tension(220.0),
        corriente=Corriente(10.0),
        potencia_activa=PotenciaActiva(2200.0),
        factor_potencia=FactorPotencia(0.95),
    )
    lectura = LecturaInstantanea(
        id=None,
        dispositivo_id="dev-test-1",
        registrado_en=datetime(2026, 9, 7, 10, 0, 0, tzinfo=timezone.utc),
        fase_r=fase_ok,
        fase_s=fase_ok,
        fase_t=fase_ok,
        potencia_activa_total=PotenciaActiva(6600.0),
    )

    t0 = datetime(2026, 9, 7, 10, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=4)

    ProcesadorAlertasIngesta.procesar_alertas(
        dispositivo=disp, mac_raw="AABBCCDDEEFF", lectura=lectura, recorded_at=t0, repo_telemetria=mock_repo
    )
    ProcesadorAlertasIngesta.procesar_alertas(
        dispositivo=disp, mac_raw="AABBCCDDEEFF", lectura=lectura, recorded_at=t1, repo_telemetria=mock_repo
    )

    assert mock_notif.notificar_alerta_critica.call_count == 0


def test_construir_mensaje_alerta_critica_formato():
    disp = _dispositivo()
    alerta = AlertaDispositivo(
        id=1,
        dispositivo_id="dev-test-1",
        tipo_alerta="CRUCE_TI_FASE",
        severidad=SeveridadAlerta.CRITICAL,
        mensaje="Inversión severa de polaridad en Fase L1",
        fase="L1",
        valor_medido=-0.45,
        valor_umbral=-0.20,
        unidad="FP",
    )
    msg = _construir_mensaje_alerta_critica(
        alerta=alerta,
        dispositivo=disp,
        destinatarios=["operaciones@datamaq.com.ar"],
        from_email="no-reply@datamaq.com.ar",
    )

    assert "CRÍTICA" in msg["Subject"]
    assert "CRUCE_TI_FASE" in msg["Subject"]
    assert msg["To"] == "operaciones@datamaq.com.ar"
    assert msg["Auto-Submitted"] == "auto-generated"
    assert msg["X-Auto-Response-Suppress"] == "All"
    assert msg["Precedence"] == "bulk"

    payload_text = msg.get_body(preferencelist=("plain",)).get_content()
    assert "Inversión severa de polaridad" in payload_text
    assert "Compresor Central" in payload_text

    payload_html = msg.get_body(preferencelist=("html",)).get_content()
    assert "Alerta Eléctrica Crítica" in payload_html
    assert "-0.45" in payload_html
