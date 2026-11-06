"""tests/unit/test_websocket_aislamiento_organizacion.py — Tests de aislamiento de datos por organización en el stream /ws/live (fuga cross-tenant)."""

from unittest.mock import MagicMock, patch

from src.application.dtos.auth_dto import PlantaAccesoDTO
from src.application.use_cases.ingesta.resolvedor_dispositivo import (
    ResolvedorDispositivoIngesta,
)
from src.domain.auth.entities import AccesoPlantaUsuario
from src.domain.telemetria.services import debe_recibir_evento
from src.infrastructure.fastapi import server
from src.infrastructure.fastapi.auth_dependencies import get_acceso_plantas_use_case
from src.infrastructure.fastapi.server import (
    ConnectedClient,
    _resolver_contexto_evento,
    _resolver_plantas_permitidas_ws,
    websocket_broadcast_callback,
)

# ---------------------------------------------------------------------------
# 1. debe_recibir_evento(): decisión pura de filtrado por organización y planta
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

    def test_cliente_con_plantas_permitidas_recibe_evento_de_su_planta(self):
        assert (
            debe_recibir_evento(
                False,
                "org-a",
                "org-a",
                plantas_permitidas=frozenset({"planta-a"}),
                planta_evento="planta-a",
            )
            is True
        )

    def test_cliente_con_plantas_permitidas_es_descartado_ante_evento_otra_planta(self):
        assert (
            debe_recibir_evento(
                False,
                "org-a",
                "org-a",
                plantas_permitidas=frozenset({"planta-a"}),
                planta_evento="planta-b",
            )
            is False
        )
        assert (
            debe_recibir_evento(
                False,
                "org-a",
                "org-a",
                plantas_permitidas=frozenset({"planta-a"}),
                planta_evento=None,
            )
            is False
        )

    def test_cliente_sin_restriccion_planta_recibe_eventos_cualquier_planta_su_org(self):
        assert (
            debe_recibir_evento(
                False,
                "org-a",
                "org-a",
                plantas_permitidas=None,
                planta_evento="planta-a",
            )
            is True
        )
        assert (
            debe_recibir_evento(
                False,
                "org-a",
                "org-a",
                plantas_permitidas=None,
                planta_evento="planta-b",
            )
            is True
        )
        assert (
            debe_recibir_evento(
                False,
                "org-a",
                "org-a",
                plantas_permitidas=None,
                planta_evento=None,
            )
            is True
        )

    def test_superadmin_recibe_cualquier_planta_cualquier_organizacion(self):
        assert (
            debe_recibir_evento(
                True,
                None,
                "org-a",
                plantas_permitidas=None,
                planta_evento="planta-a",
            )
            is True
        )
        assert (
            debe_recibir_evento(
                True,
                "org-b",
                "org-a",
                plantas_permitidas=frozenset({"planta-x"}),
                planta_evento="planta-y",
            )
            is True
        )
        assert (
            debe_recibir_evento(
                True,
                None,
                None,
                plantas_permitidas=None,
                planta_evento=None,
            )
            is True
        )


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


# ---------------------------------------------------------------------------
# 3. _resolver_contexto_evento(): mac -> (org_id, planta_id)
# ---------------------------------------------------------------------------


class TestResolverContextoEvento:
    def setup_method(self) -> None:
        ResolvedorDispositivoIngesta.limpiar_cache()

    def teardown_method(self) -> None:
        ResolvedorDispositivoIngesta.limpiar_cache()

    def test_topico_invalido_devuelve_none_none(self):
        assert _resolver_contexto_evento("invalido") == (None, None)
        assert _resolver_contexto_evento("a/b") == (None, None)

    def test_dispositivo_cacheado_con_planta_y_org_en_cache(self):
        ResolvedorDispositivoIngesta._device_cache["001122334455"] = _FakeDispositivoConPlanta(planta_id="planta-1")
        ResolvedorDispositivoIngesta._organizacion_cache["planta-1"] = "org-1"

        org, planta = _resolver_contexto_evento("pow/datamaq/00:11:22:33:44:55/telemetria")
        assert org == "org-1"
        assert planta == "planta-1"

    def test_dispositivo_sin_planta_devuelve_none_none(self):
        ResolvedorDispositivoIngesta._device_cache["001122334455"] = _FakeDispositivoConPlanta(planta_id=None)

        org, planta = _resolver_contexto_evento("pow/datamaq/00:11:22:33:44:55/telemetria")
        assert org is None
        assert planta is None


# ---------------------------------------------------------------------------
# 4. websocket_broadcast_callback(): aislamiento en vivo por planta
# ---------------------------------------------------------------------------


class TestBroadcastCallbackAislamientoPlanta:
    def setup_method(self) -> None:
        ResolvedorDispositivoIngesta.limpiar_cache()
        self._orig_active = list(server.active_websockets)
        self._orig_loop = server.async_loop
        server.active_websockets.clear()

    def teardown_method(self) -> None:
        ResolvedorDispositivoIngesta.limpiar_cache()
        server.active_websockets.clear()
        server.active_websockets.extend(self._orig_active)
        server.async_loop = self._orig_loop

    def test_broadcast_aisla_por_planta_y_organizacion(self):
        ResolvedorDispositivoIngesta._device_cache["001122334455"] = _FakeDispositivoConPlanta(planta_id="planta-1")
        ResolvedorDispositivoIngesta._organizacion_cache["planta-1"] = "org-1"

        mock_loop = MagicMock()
        mock_loop.is_closed.return_value = False
        server.async_loop = mock_loop

        ws_planta1 = MagicMock()
        ws_planta2 = MagicMock()
        ws_sin_restriccion = MagicMock()
        ws_otra_org = MagicMock()
        ws_superadmin = MagicMock()

        c_planta1 = ConnectedClient(
            websocket=ws_planta1,
            organizacion_id="org-1",
            es_superadmin=False,
            plantas_permitidas=frozenset({"planta-1"}),
        )
        c_planta2 = ConnectedClient(
            websocket=ws_planta2,
            organizacion_id="org-1",
            es_superadmin=False,
            plantas_permitidas=frozenset({"planta-2"}),
        )
        c_sin_restriccion = ConnectedClient(
            websocket=ws_sin_restriccion,
            organizacion_id="org-1",
            es_superadmin=False,
            plantas_permitidas=None,
        )
        c_otra_org = ConnectedClient(
            websocket=ws_otra_org,
            organizacion_id="org-2",
            es_superadmin=False,
            plantas_permitidas=None,
        )
        c_superadmin = ConnectedClient(
            websocket=ws_superadmin,
            organizacion_id=None,
            es_superadmin=True,
            plantas_permitidas=None,
        )

        server.active_websockets.extend([c_planta1, c_planta2, c_sin_restriccion, c_otra_org, c_superadmin])

        with patch("asyncio.run_coroutine_threadsafe") as mock_threadsafe:
            websocket_broadcast_callback(
                "pow/datamaq/00:11:22:33:44:55/telemetria",
                {"potencia_activa_kw": 12.5},
            )

            # Debe haber despachado a 3 clientes:
            # - c_planta1 (permitida planta-1)
            # - c_sin_restriccion (todas de org-1)
            # - c_superadmin (ve todo)
            # Y descartado:
            # - c_planta2 (solo permitida planta-2)
            # - c_otra_org (org-2 != org-1)
            assert mock_threadsafe.call_count == 3
            ws_planta1.send_text.assert_called_once()
            ws_sin_restriccion.send_text.assert_called_once()
            ws_superadmin.send_text.assert_called_once()
            ws_planta2.send_text.assert_not_called()
            ws_otra_org.send_text.assert_not_called()


# ---------------------------------------------------------------------------
# 5. _resolver_plantas_permitidas_ws(): handshake y consulta de permisos
# ---------------------------------------------------------------------------


class TestResolverPlantasPermitidasWs:
    def test_superadmin_devuelve_none(self):
        app = MagicMock()
        claims = {"sub": "u-admin", "rol": "superadmin", "org": "org-1"}
        assert _resolver_plantas_permitidas_ws(app, claims) is None

    def test_usuario_sin_filas_accesos_devuelve_none(self):
        app = MagicMock()
        mock_use_case = MagicMock()
        mock_use_case.repo_accesos.listar_por_usuario.return_value = []
        app.dependency_overrides = {get_acceso_plantas_use_case: lambda: mock_use_case}

        claims = {"sub": "u-1", "rol": "operador", "org": "org-1"}
        assert _resolver_plantas_permitidas_ws(app, claims) is None

    def test_usuario_con_filas_accesos_devuelve_frozenset(self):
        app = MagicMock()
        mock_use_case = MagicMock()
        mock_use_case.repo_accesos.listar_por_usuario.return_value = [
            AccesoPlantaUsuario(usuario_id="u-1", planta_id="planta-a", puede_cambiar=False)
        ]
        mock_use_case.resolver.return_value = [
            PlantaAccesoDTO(id="planta-a", nombre="Planta A", organizacion_id="org-1", puede_cambiar=False)
        ]
        app.dependency_overrides = {get_acceso_plantas_use_case: lambda: mock_use_case}

        claims = {"sub": "u-1", "rol": "operador", "org": "org-1"}
        resultado = _resolver_plantas_permitidas_ws(app, claims)
        assert resultado == frozenset({"planta-a"})
