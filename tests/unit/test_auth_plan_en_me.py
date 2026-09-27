"""tests/unit/test_auth_plan_en_me.py — estado del plan de suscripción expuesto en /me (Fase 5)."""

from datetime import datetime, timedelta, timezone

from src.application.use_cases.autenticar_usuario import AutenticarUsuarioUseCase
from src.domain.auth.ports import RepositorioUsuariosPort
from src.domain.auth.services import HashContrasenaService
from src.domain.telemetria.entities import Organizacion, PlanTelemetria, Suscripcion
from src.domain.telemetria.value_objects import VisibilidadPlan


class MockRepositorioUsuarios(RepositorioUsuariosPort):
    def obtener_por_usuario(self, usuario):
        return None

    def obtener_por_id(self, usuario_id):
        return None

    def guardar(self, usuario):
        return usuario


class MockTokenService:
    def generar(self, *args, **kwargs):
        return "token-fake"

    def verificar(self, token, secretos_adicionales=None):
        return {}


class FakeRepoSuscripciones:
    def __init__(self, suscripciones: dict[str, Suscripcion]):
        self.suscripciones = suscripciones

    def obtener_por_organizacion(self, organizacion_id):
        return self.suscripciones.get(organizacion_id)

    def guardar(self, suscripcion):
        self.suscripciones[suscripcion.organizacion_id] = suscripcion
        return suscripcion

    def listar_vencidas(self, ahora):
        return []


class FakeRepoPlanes:
    def __init__(self, planes: dict[str, PlanTelemetria]):
        self.planes = planes

    def listar_planes(self):
        return list(self.planes.values())

    def obtener_por_id(self, plan_id):
        return self.planes.get(plan_id)

    def guardar_plan(self, plan):
        self.planes[plan.id] = plan
        return plan


class FakeRepoOrganizaciones:
    def __init__(self, organizaciones: dict[str, Organizacion]):
        self.organizaciones = organizaciones

    def obtener_por_id(self, org_id):
        return self.organizaciones.get(org_id)

    def guardar(self, organizacion):
        self.organizaciones[organizacion.id] = organizacion
        return organizacion

    def listar(self):
        return list(self.organizaciones.values())


def _plan() -> PlanTelemetria:
    return PlanTelemetria(
        id="plan-pro",
        nombre="PRO",
        descripcion="Plan PRO",
        precio_mensual_ars=5000,
        visibilidad=VisibilidadPlan.PUBLICO,
        retencion_dias=365,
        granularidad_minutos=1,
        max_dispositivos=10,
        canales_notificacion=["email"],
    )


def _use_case(repo_suscripciones=None, repo_planes=None, repo_organizaciones=None) -> AutenticarUsuarioUseCase:
    return AutenticarUsuarioUseCase(
        MockRepositorioUsuarios(),
        HashContrasenaService(),
        MockTokenService(),
        480,
        repo_suscripciones=repo_suscripciones,
        repo_planes=repo_planes,
        repo_organizaciones=repo_organizaciones,
    )


def test_sin_repos_de_suscripcion_devuelve_defaults_free():
    dto = _use_case().me({"usuario": "u1", "rol": "admin", "org": "org-1"})

    assert dto.modo_free is True
    assert dto.retention_days == 7
    assert dto.notificaciones_habilitadas is False
    assert dto.plan_nombre is None


def test_sin_organizacion_devuelve_defaults_free():
    dto = _use_case(FakeRepoSuscripciones({}), FakeRepoPlanes({})).me({"usuario": "u1", "rol": "admin"})

    assert dto.modo_free is True
    assert dto.retention_days == 7


def test_organizacion_sin_fila_de_suscripcion_es_free():
    dto = _use_case(FakeRepoSuscripciones({}), FakeRepoPlanes({})).me({"usuario": "u1", "rol": "admin", "org": "org-1"})

    assert dto.modo_free is True
    assert dto.plan_nombre is None
    assert dto.notificaciones_habilitadas is False


def test_organizacion_con_pro_vigente_refleja_el_plan():
    plan = _plan()
    sus = Suscripcion(
        organizacion_id="org-1", plan_id=plan.id, pro_vence_en=datetime.now(timezone.utc) + timedelta(days=10)
    )
    dto = _use_case(FakeRepoSuscripciones({"org-1": sus}), FakeRepoPlanes({plan.id: plan})).me(
        {"usuario": "u1", "rol": "admin", "org": "org-1"}
    )

    assert dto.modo_free is False
    assert dto.plan_nombre == "PRO"
    assert dto.retention_days == 365
    assert dto.notificaciones_habilitadas is True


def test_organizacion_con_pro_vencido_es_free_aunque_tenga_plan_id():
    plan = _plan()
    sus = Suscripcion(
        organizacion_id="org-1", plan_id=plan.id, pro_vence_en=datetime.now(timezone.utc) - timedelta(days=1)
    )
    dto = _use_case(FakeRepoSuscripciones({"org-1": sus}), FakeRepoPlanes({plan.id: plan})).me(
        {"usuario": "u1", "rol": "admin", "org": "org-1"}
    )

    assert dto.modo_free is True
    assert dto.plan_nombre is None
    assert dto.notificaciones_habilitadas is False
    assert dto.retention_days == 7


def test_cooperativa_sin_suscripcion_tiene_retencion_ilimitada():
    org = Organizacion(id="coop-1", nombre="Cooperativa Test", es_cooperativa=True)
    dto = _use_case(
        FakeRepoSuscripciones({}),
        FakeRepoPlanes({}),
        FakeRepoOrganizaciones({"coop-1": org}),
    ).me({"usuario": "u1", "rol": "admin", "org": "coop-1"})

    assert dto.es_cooperativa is True
    assert dto.modo_free is False
    assert dto.plan_nombre is None
    assert dto.retention_days == 7  # fallback, pero es_cooperativa=True indica ilimitado
    assert dto.notificaciones_habilitadas is False


def test_cooperativa_con_suscripcion_pro_ignora_plan_y_usa_retencion_ilimitada():
    org = Organizacion(id="coop-2", nombre="Cooperativa con Pro", es_cooperativa=True)
    plan = _plan()
    sus = Suscripcion(
        organizacion_id="coop-2", plan_id=plan.id, pro_vence_en=datetime.now(timezone.utc) + timedelta(days=10)
    )
    dto = _use_case(
        FakeRepoSuscripciones({"coop-2": sus}),
        FakeRepoPlanes({plan.id: plan}),
        FakeRepoOrganizaciones({"coop-2": org}),
    ).me({"usuario": "u1", "rol": "admin", "org": "coop-2"})

    assert dto.es_cooperativa is True
    assert dto.modo_free is False
    assert dto.plan_nombre is None  # no refleja plan aunque tenga suscripcion vigente
    assert dto.retention_days == 7  # fallback, pero es_cooperativa=True indica ilimitado
    assert dto.notificaciones_habilitadas is False
