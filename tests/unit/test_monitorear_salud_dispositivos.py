# tests/unit/test_monitorear_salud_dispositivos.py
from datetime import datetime, timedelta, timezone

from src.application.use_cases.ingesta.resolvedor_dispositivo import (
    ResolvedorDispositivoIngesta,
)
from src.application.use_cases.ingestar_telemetria import IngestarTelemetriaUseCase
from src.application.use_cases.monitorear_salud_dispositivos import (
    MonitorearSaludDispositivosUseCase,
)
from src.domain.telemetria.value_objects import (
    EstadoDispositivo,
    MacAddress,
    ReglaAlertaConectividad,
    SeveridadAlerta,
)
from tests.unit.test_optimizacion_db import MockDispositivosRepo, MockTelemetriaRepo


def test_monitorear_salud_dispositivos_detecta_corte_y_auto_resuelve():
    repo_dev = MockDispositivosRepo()
    repo_tel = MockTelemetriaRepo()

    mac_str = "F8B3B7C0BBB0"
    mac = MacAddress(mac_str)

    usecase_ingesta = IngestarTelemetriaUseCase(
        repo_dispositivos=repo_dev,
        repo_telemetria=repo_tel,
        granularidad_segundos=0,
    )

    ahora = datetime.now(timezone.utc)
    hace_10_min = ahora - timedelta(minutes=10)

    # 1. Ingestar telemetría previa para registrar el dispositivo
    payload_inst = {
        "device_info": {"mac": mac_str, "model": "SmartPlus"},
        "timestamp": hace_10_min.isoformat(),
        "phase_r": {"v": 220.0, "i": 10.0, "p": 2200.0, "pf": 0.98},
    }
    usecase_ingesta.ejecutar(f"m/wifi/{mac_str}/inst", payload_inst)

    dev = repo_dev.obtener_por_uid(mac)
    assert dev is not None
    assert dev.estado == EstadoDispositivo.ONLINE
    assert dev.visto_por_ultima_vez is not None

    # Forzar fecha visto_por_ultima_vez a hace 10 minutos
    dev.visto_por_ultima_vez = hace_10_min
    repo_dev.guardar(dev)

    # 2. Ejecutar Watchdog MonitorearSaludDispositivosUseCase
    regla = ReglaAlertaConectividad(timeout_segundos=300)  # 5 min
    watchdog = MonitorearSaludDispositivosUseCase(
        repo_dispositivos=repo_dev,
        repo_telemetria=repo_tel,
        regla=regla,
    )

    alertas = watchdog.ejecutar(ahora=ahora)

    # Verificar que se generó la alerta crítica
    assert len(alertas) == 1
    assert alertas[0].tipo_alerta == "PÉRDIDA_COMUNICACIÓN"
    assert alertas[0].severidad == SeveridadAlerta.CRITICAL.value
    assert alertas[0].categoria == "CONECTIVIDAD"

    # Verificar que el dispositivo pasó a OFFLINE
    dev_actualizado = repo_dev.obtener_por_uid(mac)
    assert dev_actualizado.estado == EstadoDispositivo.OFFLINE

    # 3. Simular recuperación: el medidor vuelve a enviar telemetría
    hace_1_seg = ahora + timedelta(seconds=5)
    payload_recuperacion = {
        "device_info": {"mac": mac_str, "model": "SmartPlus"},
        "timestamp": hace_1_seg.isoformat(),
        "phase_r": {"v": 220.0, "i": 10.0, "p": 2200.0, "pf": 0.98},
    }
    usecase_ingesta.ejecutar(f"m/wifi/{mac_str}/inst", payload_recuperacion)

    # Verificar que la alerta previa de PÉRDIDA_COMUNICACIÓN fue auto-resuelta
    alertas_abiertas = repo_tel.listar_alertas(dispositivo_id=dev.id, solo_abiertas=True)
    assert not any(a.tipo_alerta == "PÉRDIDA_COMUNICACIÓN" for a in alertas_abiertas)


def test_evaluar_conectividad_inestable_wifi():
    ResolvedorDispositivoIngesta.limpiar_cache()
    repo_dev = MockDispositivosRepo()
    repo_tel = MockTelemetriaRepo()

    mac_str = "F8B3B7C0BBB0"
    mac_vo = MacAddress(mac_str)
    usecase_ingesta = IngestarTelemetriaUseCase(
        repo_dispositivos=repo_dev,
        repo_telemetria=repo_tel,
        granularidad_segundos=0,
    )

    ahora = datetime.now(timezone.utc)

    # Primero registrar el dispositivo con un mensaje de instantánea
    payload_inst = {
        "device_info": {"mac": mac_str, "model": "SmartPlus"},
        "timestamp": ahora.isoformat(),
        "phase_r": {"v": 220.0, "i": 10.0, "p": 2200.0, "pf": 0.98},
    }
    usecase_ingesta.ejecutar(f"m/wifi/{mac_str}/inst", payload_inst)

    # Ingestar status log con señal Wi-Fi degradada (RSSI -85 dBm < -78 dBm)
    payload_status_degradado = {
        "device_info": {"mac": mac_str, "model": "SmartPlus"},
        "timestamp": ahora.isoformat(),
        "wifi": {"rssi": -85, "quality": 30},
        "ip": "201.212.226.86",
        "uptime": 1200,
    }
    usecase_ingesta.ejecutar(f"m/wifi/{mac_str}/status", payload_status_degradado)

    dev = repo_dev.obtener_por_uid(mac_vo)
    assert dev is not None

    # Verificar que se generó alerta WARNING de inestabilidad
    alertas = repo_tel.listar_alertas(dispositivo_id=dev.id, solo_abiertas=True)
    alerta_inestable = [a for a in alertas if a.tipo_alerta == "CONECTIVIDAD_INESTABLE"]
    assert len(alerta_inestable) == 1
    assert alerta_inestable[0].severidad == SeveridadAlerta.WARNING
