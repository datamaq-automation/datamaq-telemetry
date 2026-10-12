"""tests/unit/test_vigilancia_conectividad.py — Bucle que corre el monitor de conectividad con la configuración (#19)."""

import asyncio
from unittest.mock import MagicMock, patch

from src.infrastructure.fastapi import vigilancia_conectividad
from src.infrastructure.settings.config import Settings


def test_la_vigilancia_usa_el_umbral_y_la_alerta_de_la_configuracion():
    settings = Settings(DISPOSITIVO_OFFLINE_TIMEOUT_S=1200, DISPOSITIVO_OFFLINE_ALERTA_HABILITADA=False)
    with (
        patch.object(vigilancia_conectividad, "get_session_factory", return_value=lambda: MagicMock()),
        patch.object(vigilancia_conectividad, "MonitorearSaludDispositivosUseCase") as monitor_cls,
    ):
        monitor_cls.return_value.ejecutar.return_value = []
        assert vigilancia_conectividad.vigilar_conectividad_una_vez(settings) == 0

    kwargs = monitor_cls.call_args.kwargs
    assert kwargs["regla"].timeout_segundos == 1200
    assert kwargs["generar_alerta"] is False


def test_por_defecto_la_alerta_de_offline_esta_apagada():
    campos = Settings.model_fields
    assert campos["DISPOSITIVO_OFFLINE_ALERTA_HABILITADA"].default is False
    assert campos["DISPOSITIVO_OFFLINE_TIMEOUT_S"].default == 900


def test_el_bucle_loguea_el_error_y_sigue():
    esperas = iter([None, asyncio.CancelledError()])

    async def _sleep(_s: float) -> None:
        resultado = next(esperas)
        if resultado is not None:
            raise resultado

    with (
        patch.object(vigilancia_conectividad.asyncio, "sleep", side_effect=_sleep),
        patch.object(vigilancia_conectividad, "vigilar_conectividad_una_vez", side_effect=RuntimeError("db caida")),
        patch.object(vigilancia_conectividad, "logger") as logger,
    ):
        asyncio.run(vigilancia_conectividad.loop_vigilancia_conectividad())
    logger.warning.assert_called_once_with("vigilancia_conectividad_fallida", error="db caida")


def test_la_api_arranca_el_bucle_en_el_lifespan():
    from src.infrastructure.fastapi import server

    assert server.loop_vigilancia_conectividad is vigilancia_conectividad.loop_vigilancia_conectividad
