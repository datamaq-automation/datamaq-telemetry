"""tests/unit/test_websocket_aislamiento_organizacion.py — Tests de aislamiento de datos por organización en el stream /ws/live (fuga cross-tenant)."""

from unittest.mock import MagicMock

from src.application.use_cases.ingesta.resolvedor_dispositivo import (
    ResolvedorDispositivoIngesta,
)
from src.domain.telemetria.services import debe_recibir_evento

# ---------------------------------------------------------------------------
# 1. debe_recibir_evento(): decisión pura de filtrado por organización
# ---------------------------------------------------------------------------


class TestDebeRecibirEvento:
    def test_superadmin_ve_todo(self):
        assert debe_recibir_evento(True, None, "org-a") is True
        assert debe_recibir_evento(True, "org-b", "org-a") is True
        assert debe_recibir_evento(True, None, None) is True

    def test_misma_organizacion_ve_el_evento(self):
        assert debe_recibir_evento(False, "org-a", "org-a") is True

    def test_organizacion_distinta_no_ve_el_evento(self):
        assert debe_recibir_evento(False, "org-a", "org-b") is False

    def test_evento_sin_organizacion_resuelta_solo_lo_ve_superadmin(self):
        assert debe_recibir_evento(False, "org-a", None) is False
        assert debe_recibir_evento(True, "org-a", None) is True

    def test_cliente_sin_organizacion_no_ve_eventos_de_organizaciones(self):
        assert debe_recibir_evento(False, None, "org-a") is False


# ---------------------------------------------------------------------------
# 2. ResolvedorDispositivoIngesta.resolver_organizacion_id(): mac -> planta -> org
# ---------------------------------------------------------------------------


class _FakeDispositivoConPlanta:
    def __init__(self, planta_id: str | None) -> None:
        self.planta_id = planta_id


class _FakePlanta:
    def __init__(self, organizacion_id: str | None) -> None:
        self.organizacion_id = organizacion_id


class TestResolverOrganizacionId:
    def setup_method(self) -> None:
        ResolvedorDispositivoIngesta.limpiar_cache()

    def teardown_method(self) -> None:
        ResolvedorDispositivoIngesta.limpiar_cache()

    def test_dispositivo_no_cacheado_devuelve_none(self):
        repo_organizaciones = MagicMock()
        resultado = ResolvedorDispositivoIngesta.resolver_organizacion_id("AABBCCDDEEFF", repo_organizaciones)
        assert resultado is None
        repo_organizaciones.obtener_planta_por_id.assert_not_called()

    def test_dispositivo_sin_planta_devuelve_none(self):
        ResolvedorDispositivoIngesta._device_cache["AABBCCDDEEFF"] = _FakeDispositivoConPlanta(planta_id=None)
        repo_organizaciones = MagicMock()

        resultado = ResolvedorDispositivoIngesta.resolver_organizacion_id("AABBCCDDEEFF", repo_organizaciones)

        assert resultado is None
        repo_organizaciones.obtener_planta_por_id.assert_not_called()

    def test_resuelve_organizacion_via_planta_y_cachea(self):
        ResolvedorDispositivoIngesta._device_cache["AABBCCDDEEFF"] = _FakeDispositivoConPlanta(planta_id="planta-1")
        repo_organizaciones = MagicMock()
        repo_organizaciones.obtener_planta_por_id.return_value = _FakePlanta(organizacion_id="org-a")

        resultado = ResolvedorDispositivoIngesta.resolver_organizacion_id("AABBCCDDEEFF", repo_organizaciones)
        assert resultado == "org-a"
        repo_organizaciones.obtener_planta_por_id.assert_called_once_with("planta-1")

        # Segunda llamada: debe servirse desde la caché planta->org, sin volver a golpear el repo.
        resultado_2 = ResolvedorDispositivoIngesta.resolver_organizacion_id("AABBCCDDEEFF", repo_organizaciones)
        assert resultado_2 == "org-a"
        repo_organizaciones.obtener_planta_por_id.assert_called_once_with("planta-1")

    def test_planta_sin_organizacion_devuelve_none_y_cachea(self):
        ResolvedorDispositivoIngesta._device_cache["AABBCCDDEEFF"] = _FakeDispositivoConPlanta(planta_id="planta-2")
        repo_organizaciones = MagicMock()
        repo_organizaciones.obtener_planta_por_id.return_value = _FakePlanta(organizacion_id=None)

        resultado = ResolvedorDispositivoIngesta.resolver_organizacion_id("AABBCCDDEEFF", repo_organizaciones)
        assert resultado is None
        repo_organizaciones.obtener_planta_por_id.assert_called_once_with("planta-2")

    def test_planta_inexistente_devuelve_none(self):
        ResolvedorDispositivoIngesta._device_cache["AABBCCDDEEFF"] = _FakeDispositivoConPlanta(planta_id="planta-3")
        repo_organizaciones = MagicMock()
        repo_organizaciones.obtener_planta_por_id.return_value = None

        resultado = ResolvedorDispositivoIngesta.resolver_organizacion_id("AABBCCDDEEFF", repo_organizaciones)
        assert resultado is None
