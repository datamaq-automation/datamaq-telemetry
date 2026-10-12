"""tests/unit/test_dispositivo_offline_por_inactividad.py — Estado OFFLINE por inactividad (#19).

El monitor de salud existía pero nada lo invocaba: Durax y Hogar seguían ONLINE horas después de su último dato.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

from src.application.use_cases.ingesta.resolvedor_dispositivo import ResolvedorDispositivoIngesta
from src.application.use_cases.ingestar_telemetria import IngestarTelemetriaUseCase
from src.application.use_cases.monitorear_salud_dispositivos import MonitorearSaludDispositivosUseCase
from src.domain.telemetria.value_objects import EstadoDispositivo, MacAddress, ReglaAlertaConectividad
from tests.unit.test_optimizacion_db import MockDispositivosRepo, MockTelemetriaRepo

MAC = "D48C49F03564"
REGLA_900 = ReglaAlertaConectividad(timeout_segundos=900)


def _inst(momento: datetime) -> dict[str, Any]:
    return {
        "device_info": {"mac": MAC, "model": "SmartPlus"},
        "timestamp": momento.isoformat(),
        "phase_r": {"v": 220.0, "i": 10.0, "p": 2200.0, "pf": 0.98},
    }


def _entorno() -> tuple[MockDispositivosRepo, MockTelemetriaRepo, IngestarTelemetriaUseCase]:
    ResolvedorDispositivoIngesta.limpiar_cache()
    repo_dev, repo_tel = MockDispositivosRepo(), MockTelemetriaRepo()
    ingesta = IngestarTelemetriaUseCase(repo_dispositivos=repo_dev, repo_telemetria=repo_tel, granularidad_segundos=0)
    return repo_dev, repo_tel, ingesta


def _estado(repo_dev: MockDispositivosRepo) -> EstadoDispositivo:
    dev = repo_dev.obtener_por_uid(MacAddress(MAC))
    assert dev is not None
    return dev.estado


def test_ciclo_online_offline_online():
    repo_dev, repo_tel, ingesta = _entorno()
    t0 = datetime.now(timezone.utc) - timedelta(hours=1)
    ingesta.ejecutar(f"m/wifi/{MAC}/inst", _inst(t0))
    assert _estado(repo_dev) == EstadoDispositivo.ONLINE

    monitor = MonitorearSaludDispositivosUseCase(repo_dev, repo_tel, regla=REGLA_900, generar_alerta=False)
    monitor.ejecutar(ahora=t0 + timedelta(seconds=901))
    assert _estado(repo_dev) == EstadoDispositivo.OFFLINE

    ingesta.ejecutar(f"m/wifi/{MAC}/inst", _inst(t0 + timedelta(seconds=960)))
    assert _estado(repo_dev) == EstadoDispositivo.ONLINE


def test_sin_superar_el_umbral_sigue_online():
    """900 s alcanzan para el intervalo normal de 300 s: un mensaje demorado no hace oscilar el estado."""
    repo_dev, repo_tel, ingesta = _entorno()
    t0 = datetime.now(timezone.utc) - timedelta(hours=1)
    ingesta.ejecutar(f"m/wifi/{MAC}/inst", _inst(t0))

    MonitorearSaludDispositivosUseCase(repo_dev, repo_tel, regla=REGLA_900).ejecutar(ahora=t0 + timedelta(seconds=600))

    assert _estado(repo_dev) == EstadoDispositivo.ONLINE


def test_con_la_alerta_apagada_marca_offline_sin_abrir_alerta():
    repo_dev, repo_tel, ingesta = _entorno()
    t0 = datetime.now(timezone.utc) - timedelta(hours=1)
    ingesta.ejecutar(f"m/wifi/{MAC}/inst", _inst(t0))
    logger = MagicMock()

    alertas = MonitorearSaludDispositivosUseCase(
        repo_dev, repo_tel, logger=logger, regla=REGLA_900, generar_alerta=False
    ).ejecutar(ahora=t0 + timedelta(hours=2))

    assert alertas == []
    assert not any(a.tipo_alerta == "PÉRDIDA_COMUNICACIÓN" for a in repo_tel.listar_alertas())
    assert _estado(repo_dev) == EstadoDispositivo.OFFLINE
    logger.info.assert_any_call(
        "dispositivo_marcado_offline",
        dispositivo_id=repo_dev.obtener_por_uid(MacAddress(MAC)).id,
        mac=MAC,
        segundos_inactivo=7200,
    )


def test_dispositivo_desactivado_no_se_toca():
    repo_dev, repo_tel, ingesta = _entorno()
    t0 = datetime.now(timezone.utc) - timedelta(hours=1)
    ingesta.ejecutar(f"m/wifi/{MAC}/inst", _inst(t0))
    dev = repo_dev.obtener_por_uid(MacAddress(MAC))
    assert dev is not None
    dev.esta_activo = False

    MonitorearSaludDispositivosUseCase(repo_dev, repo_tel, regla=REGLA_900).ejecutar(ahora=t0 + timedelta(hours=2))

    assert _estado(repo_dev) == EstadoDispositivo.ONLINE


def test_el_monitor_no_reescribe_el_dispositivo_entero():
    repo_dev, repo_tel, ingesta = _entorno()
    t0 = datetime.now(timezone.utc) - timedelta(hours=1)
    ingesta.ejecutar(f"m/wifi/{MAC}/inst", _inst(t0))
    repo_dev.guardar = MagicMock(side_effect=AssertionError("no debe usar guardar"))

    MonitorearSaludDispositivosUseCase(repo_dev, repo_tel, regla=REGLA_900, generar_alerta=False).ejecutar(
        ahora=t0 + timedelta(hours=2)
    )

    assert _estado(repo_dev) == EstadoDispositivo.OFFLINE
