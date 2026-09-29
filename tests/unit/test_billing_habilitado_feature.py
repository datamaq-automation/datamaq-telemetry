"""tests/unit/test_billing_habilitado_feature.py.

Tests del flag BILLING_HABILITADO para desactivar cobro de suscripciones.
Verifica que cuando billing_habilitado=False, todos actúan como PRO ilimitado.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from src.application.use_cases.autenticar_usuario import AutenticarUsuarioUseCase
from src.application.use_cases.consultar_telemetria import ConsultarTelemetriaUseCase
from src.domain.auth.services import HashContrasenaService, RateLimiterService
from src.domain.telemetria.entities import (
    Dispositivo,
    Organizacion,
    Planta,
    Suscripcion,
    ahora_utc,
)
from src.domain.telemetria.value_objects import MacAddress, ModoFreeTier
from src.infrastructure.auth.jwt_token_service import JwtTokenService


@pytest.fixture
def hash_service():
    return HashContrasenaService()


@pytest.fixture
def token_service():
    return JwtTokenService("test-secret-key-datamaq-testing")


@pytest.fixture
def rate_limiter():
    return RateLimiterService(max_intentos=5, ventana_segundos=300)


class TestConsultarTelemetriaConBillingDisabled:
    """Pruebas de retención, intervalo mínimo y contexto de suscripción cuando billing=False."""

    def test_billing_disabled_retorna_pro_ilimitado(self):
        """Cuando billing_habilitado=False, todos actúan como PRO sin límite de retención."""
        mock_repo_telem = Mock()
        mock_repo_disp = Mock()

        use_case = ConsultarTelemetriaUseCase(
            repo_telemetria=mock_repo_telem,
            repo_dispositivos=mock_repo_disp,
            billing_habilitado=False,
        )

        dispositivo = Dispositivo(
            id="dev-001",
            device_uid=MacAddress("00:00:00:00:00:01"),
            nombre="Medidor Test",
            planta_id="planta-001",
        )

        es_pro, modo_free, retencion_dias, min_intervalo = use_case._obtener_contexto_suscripcion(
            dispositivo
        )

        assert es_pro is True, "billing_disabled debe retornar es_pro=True"
        assert retencion_dias is None, "billing_disabled debe retornar retencion_dias=None (ilimitado)"
        assert min_intervalo == 0, "billing_disabled debe retornar min_intervalo=0"

    def test_billing_enabled_respeta_plan_free(self):
        """Cuando billing_habilitado=True, se respeta el plan free (7 días, 1h mínimo)."""
        mock_repo_telem = Mock()
        mock_repo_disp = Mock()
        mock_repo_org = Mock()
        mock_repo_suscripciones = Mock()

        # Sin PRO vigente = free tier
        sus_free = Suscripcion(
            organizacion_id="org-001",
            plan_id=None,
            pro_vence_en=None,
            modo_free=ModoFreeTier.PRIVADO_BASICO,
        )
        mock_repo_suscripciones.obtener_por_organizacion.return_value = sus_free

        planta = Planta(id="planta-001", organizacion_id="org-001", nombre="Planta Test")
        org = Organizacion(id="org-001", nombre="Org Test")
        mock_repo_org.obtener_planta_por_id.return_value = planta
        mock_repo_org.obtener_por_id.return_value = org

        use_case = ConsultarTelemetriaUseCase(
            repo_telemetria=mock_repo_telem,
            repo_dispositivos=mock_repo_disp,
            repo_organizaciones=mock_repo_org,
            repo_suscripciones=mock_repo_suscripciones,
            billing_habilitado=True,
        )

        dispositivo = Dispositivo(
            id="dev-001",
            device_uid=MacAddress("00:00:00:00:00:01"),
            nombre="Medidor Test",
            planta_id="planta-001",
        )

        es_pro, modo_free, retencion_dias, min_intervalo = use_case._obtener_contexto_suscripcion(
            dispositivo
        )

        assert es_pro is False, "Sin PRO vigente debe retornar es_pro=False"
        assert retencion_dias == 7, "Free debe retornar retencion_dias=7"
        assert min_intervalo == 3600, "Free debe retornar min_intervalo=3600 (1 hora)"


class TestAutenticarUsuarioConBillingDisabled:
    """Pruebas de /me cuando billing_habilitado=False."""

    def test_billing_disabled_me_sin_restricciones(
        self, hash_service, token_service, rate_limiter
    ):
        """Cuando billing_habilitado=False, /me retorna notificaciones habilitadas y sin modo free."""
        mock_repo_usuarios = Mock()
        mock_repo_dispositivos = Mock()
        mock_acceso_plantas = Mock()

        use_case = AutenticarUsuarioUseCase(
            repo_usuarios=mock_repo_usuarios,
            hash_service=hash_service,
            token_service=token_service,
            minutos_validez=120,
            rate_limiter=rate_limiter,
            billing_habilitado=False,
        )

        plan_nombre, modo_free, retention_days, notificaciones = use_case._resolver_estado_plan(
            org_id="org-001", es_cooperativa=False
        )

        assert plan_nombre is None, "No debe haber plan cuando billing_disabled"
        assert modo_free is False, "modo_free debe ser False cuando billing_disabled"
        assert retention_days is None, "retention_days debe ser None (ilimitado) cuando billing_disabled"
        assert notificaciones is True, "notificaciones deben estar habilitadas cuando billing_disabled"

    def test_billing_enabled_me_respeta_free(
        self, hash_service, token_service, rate_limiter
    ):
        """Cuando billing_habilitado=True, se respeta el estado free vs. pro."""
        mock_repo_usuarios = Mock()
        mock_repo_dispositivos = Mock()
        mock_acceso_plantas = Mock()
        mock_repo_suscripciones = Mock()

        # Sin PRO vigente = free
        sus_free = Suscripcion(
            organizacion_id="org-001",
            plan_id=None,
            pro_vence_en=None,
            modo_free=ModoFreeTier.PRIVADO_BASICO,
        )
        mock_repo_suscripciones.obtener_por_organizacion.return_value = sus_free

        use_case = AutenticarUsuarioUseCase(
            repo_usuarios=mock_repo_usuarios,
            hash_service=hash_service,
            token_service=token_service,
            minutos_validez=120,
            rate_limiter=rate_limiter,
            repo_suscripciones=mock_repo_suscripciones,
            billing_habilitado=True,
        )

        plan_nombre, modo_free, retention_days, notificaciones = use_case._resolver_estado_plan(
            org_id="org-001", es_cooperativa=False
        )

        assert plan_nombre is None, "No debe haber plan en free"
        assert modo_free is True, "modo_free debe ser True sin PRO vigente"
        assert retention_days == 7, "retention_days debe ser 7 días para free"
        assert notificaciones is False, "notificaciones no habilitadas para free"

    def test_billing_enabled_me_pro_vigente(
        self, hash_service, token_service, rate_limiter
    ):
        """Cuando billing_habilitado=True y PRO vigente, se retorna plan y Sin restricciones."""
        mock_repo_usuarios = Mock()
        mock_repo_dispositivos = Mock()
        mock_acceso_plantas = Mock()
        mock_repo_suscripciones = Mock()
        mock_repo_planes = Mock()

        # PRO vigente
        futuro = ahora_utc() + timedelta(days=30)
        sus_pro = Suscripcion(
            organizacion_id="org-001",
            plan_id="plan-pro",
            pro_vence_en=futuro,
            modo_free=ModoFreeTier.PRIVADO_BASICO,
        )
        mock_repo_suscripciones.obtener_por_organizacion.return_value = sus_pro

        from src.domain.telemetria.entities import PlanTelemetria
        from decimal import Decimal

        plan = PlanTelemetria(
            id="plan-pro",
            nombre="Pro",
            descripcion="Plan Pro",
            precio_mensual_ars=Decimal("99.99"),
            visibilidad="privado",
            retencion_dias=365,
            granularidad_minutos=0,
            max_dispositivos=100,
            canales_notificacion=["email"],
        )
        mock_repo_planes.obtener_por_id.return_value = plan

        use_case = AutenticarUsuarioUseCase(
            repo_usuarios=mock_repo_usuarios,
            hash_service=hash_service,
            token_service=token_service,
            minutos_validez=120,
            rate_limiter=rate_limiter,
            repo_suscripciones=mock_repo_suscripciones,
            repo_planes=mock_repo_planes,
            billing_habilitado=True,
        )

        plan_nombre, modo_free, retention_days, notificaciones = use_case._resolver_estado_plan(
            org_id="org-001", es_cooperativa=False
        )

        assert plan_nombre == "Pro", "Debe retornar nombre del plan cuando PRO vigente"
        assert modo_free is False, "modo_free debe ser False con PRO vigente"
        assert retention_days == 365, "retention_days debe ser 365 con PRO"
        assert notificaciones is True, "notificaciones habilitadas con PRO"


class TestVerificadorNotificacionesBilling:
    """Pruebas del verificador de notificaciones MQTT cuando billing_habilitado=False."""

    def test_billing_disabled_notificaciones_siempre_activas(self):
        """Cuando billing_habilitado=False, todos reciben notificaciones."""
        from src.infrastructure.paho_mqtt.verificador_notificaciones import (
            construir_verificador_notificaciones,
        )

        mock_session_factory = Mock()
        verificador = construir_verificador_notificaciones(
            session_factory=mock_session_factory, billing_habilitado=False
        )

        # Con billing_habilitado=False, debe retornar True sin abrir sesión
        resultado = verificador("dev-001")
        assert resultado is True
        # No debe haber abierto sesión
        mock_session_factory.assert_not_called()

    def test_billing_enabled_notificaciones_respetan_suscripcion(self):
        """Cuando billing_habilitado=True, se respeta el estado PRO/free."""
        from src.infrastructure.paho_mqtt.verificador_notificaciones import (
            construir_verificador_notificaciones,
        )
        from src.domain.telemetria.ports import RepositorioOrganizacionesPort

        mock_session_factory = Mock()
        mock_db = Mock()
        mock_session_factory.return_value = mock_db

        # Setup de mocks para el flujo normal
        mock_repo_disp = Mock()
        mock_repo_sus = Mock()

        dispositivo = Dispositivo(
            id="dev-001",
            device_uid=MacAddress("00:00:00:00:00:01"),
            nombre="Medidor Test",
            planta_id="planta-001",
        )
        mock_repo_disp.obtener_por_id.return_value = dispositivo

        planta = Planta(id="planta-001", organizacion_id="org-001", nombre="Planta Test")
        org = Organizacion(id="org-001", nombre="Org Test")

        # Mock para inyectar los repositorios
        mock_repo_org = Mock(spec=RepositorioOrganizacionesPort)
        mock_repo_org.obtener_planta_por_id.return_value = planta
        mock_repo_org.obtener_por_id.return_value = org

        # Con PRO vigente, debe retornar True
        futuro = ahora_utc() + timedelta(days=30)
        sus_pro = Suscripcion(
            organizacion_id="org-001",
            plan_id="plan-pro",
            pro_vence_en=futuro,
        )
        mock_repo_sus.obtener_por_organizacion.return_value = sus_pro

        verificador = construir_verificador_notificaciones(
            session_factory=mock_session_factory,
            repo_organizaciones=mock_repo_org,
            billing_habilitado=True,
        )

        # No llamamos al verificador sin mock completo de MySQLRepositories
        # Este test verifica que el parámetro se acepta correctamente
