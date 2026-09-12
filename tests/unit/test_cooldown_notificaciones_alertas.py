"""tests/unit/test_cooldown_notificaciones_alertas.py."""
from datetime import datetime, timedelta, timezone

from src.domain.telemetria.servicios.cooldown_notificaciones import (
    CooldownNotificacionesAlertasService,
)


def _ahora(segundos: float = 0.0) -> datetime:
    return datetime(2026, 9, 7, 10, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=segundos)


def test_cooldown_permite_primera_notificacion():
    servicio = CooldownNotificacionesAlertasService(cooldown_segundos=1800.0)
    assert servicio.debe_notificar("dev-1", "CRUCE_TI_FASE", _ahora(0)) is True


def test_cooldown_bloquea_dentro_del_intervalo():
    servicio = CooldownNotificacionesAlertasService(cooldown_segundos=1800.0)
    t0 = _ahora(0)
    servicio.registrar_notificacion("dev-1", "CRUCE_TI_FASE", t0)

    # 10 minutos después (600s < 1800s) -> Bloqueado
    assert servicio.debe_notificar("dev-1", "CRUCE_TI_FASE", _ahora(600)) is False
    # 29 minutos después (1740s < 1800s) -> Bloqueado
    assert servicio.debe_notificar("dev-1", "CRUCE_TI_FASE", _ahora(1740)) is False


def test_cooldown_permite_tras_expiracion():
    servicio = CooldownNotificacionesAlertasService(cooldown_segundos=1800.0)
    t0 = _ahora(0)
    servicio.registrar_notificacion("dev-1", "CRUCE_TI_FASE", t0)

    # 30 minutos exactos después (1800s) -> Permitido
    assert servicio.debe_notificar("dev-1", "CRUCE_TI_FASE", _ahora(1800)) is True
    # 45 minutos después (2700s) -> Permitido
    assert servicio.debe_notificar("dev-1", "CRUCE_TI_FASE", _ahora(2700)) is True


def test_cooldown_diferencia_dispositivos_y_alertas():
    servicio = CooldownNotificacionesAlertasService(cooldown_segundos=1800.0)
    t0 = _ahora(0)
    servicio.registrar_notificacion("dev-1", "CRUCE_TI_FASE", t0)

    # Otro tipo de alerta para el mismo dispositivo -> Permitido
    assert servicio.debe_notificar("dev-1", "DESBALANCE_CORRIENTE_CRITICAL", _ahora(60)) is True
    # Mismo tipo de alerta para otro dispositivo -> Permitido
    assert servicio.debe_notificar("dev-2", "CRUCE_TI_FASE", _ahora(60)) is True


def test_resetear_y_limpiar():
    servicio = CooldownNotificacionesAlertasService(cooldown_segundos=1800.0)
    t0 = _ahora(0)
    servicio.registrar_notificacion("dev-1", "CRUCE_TI_FASE", t0)
    assert servicio.debe_notificar("dev-1", "CRUCE_TI_FASE", _ahora(60)) is False

    servicio.resetear("dev-1", "CRUCE_TI_FASE")
    assert servicio.debe_notificar("dev-1", "CRUCE_TI_FASE", _ahora(60)) is True

    servicio.registrar_notificacion("dev-1", "CRUCE_TI_FASE", _ahora(60))
    servicio.limpiar()
    assert servicio.debe_notificar("dev-1", "CRUCE_TI_FASE", _ahora(60)) is True
