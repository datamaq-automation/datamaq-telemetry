"""tests/unit/test_planes.py — Pruebas unitarias del dominio y caso de uso de planes de telemetría freemium."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.application.dtos.plan_dto import PlanCreateDTO
from src.application.mappers.plan_mapper import PlanMapper
from src.application.use_cases.gestionar_planes import GestionarPlanesUseCase
from src.domain.telemetria.entities import PlanTelemetria
from src.domain.telemetria.ports import RepositorioPlanesPort
from src.domain.telemetria.services import PoliticaRetencionService
from src.domain.telemetria.value_objects import VisibilidadPlan


def _plan_publico(plan_id: str = "plan-0") -> PlanTelemetria:
    return PlanTelemetria(
        id=plan_id,
        nombre="Freemium Público",
        descripcion="Telemetría gratuita de demostración",
        precio_mensual_ars=Decimal("0"),
        visibilidad=VisibilidadPlan.PUBLICO,
        retencion_dias=7,
        granularidad_minutos=5,
        max_dispositivos=1,
        canales_notificacion=["email", "telegram"],
    )


def _plan_privado(plan_id: str = "plan-1") -> PlanTelemetria:
    return PlanTelemetria(
        id=plan_id,
        nombre="Freemium Privado",
        descripcion="Telemetría privada para plantas",
        precio_mensual_ars=Decimal("15000"),
        visibilidad=VisibilidadPlan.PRIVADO,
        retencion_dias=7,
        granularidad_minutos=5,
        max_dispositivos=1,
        canales_notificacion=["email", "telegram", "whatsapp"],
    )


class MockPlanesRepo(RepositorioPlanesPort):
    def __init__(self, planes: list[PlanTelemetria] | None = None):
        self.planes = planes or []

    def listar_planes(self) -> list[PlanTelemetria]:
        return list(self.planes)

    def obtener_por_id(self, plan_id: str) -> PlanTelemetria | None:
        for plan in self.planes:
            if plan.id == plan_id:
                return plan
        return None

    def guardar_plan(self, plan: PlanTelemetria) -> PlanTelemetria:
        self.planes.append(plan)
        return plan


def test_visibilidad_plan_enum():
    assert VisibilidadPlan.PUBLICO.value == "PUBLICO"
    assert VisibilidadPlan.PRIVADO.value == "PRIVADO"


def test_plan_telemetria_valido():
    plan = _plan_publico()
    assert plan.nombre == "Freemium Público"
    assert plan.precio_mensual_ars == Decimal("0")
    assert plan.visibilidad == VisibilidadPlan.PUBLICO
    assert plan.retencion_dias == 7
    assert plan.granularidad_minutos == 5
    assert plan.max_dispositivos == 1
    assert plan.canales_notificacion == ["email", "telegram"]


def test_politica_retencion_ventana():
    plan = _plan_publico()
    ahora = datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone.utc)
    ventana = PoliticaRetencionService.ventana_consulta(plan, ahora)
    assert ventana == ahora - timedelta(days=7)


def test_listar_catalogo_solo_publicos():
    repo = MockPlanesRepo([_plan_publico(), _plan_privado()])
    use_case = GestionarPlanesUseCase(repo)

    todos = use_case.listar_catalogo()
    assert len(todos) == 2

    publicos = use_case.listar_catalogo(solo_publicos=True)
    assert len(publicos) == 1
    assert publicos[0].id == "plan-0"
    assert publicos[0].visibilidad == VisibilidadPlan.PUBLICO


def test_crear_plan():
    repo = MockPlanesRepo()
    use_case = GestionarPlanesUseCase(repo)

    dto = PlanCreateDTO(
        nombre="Profesional",
        descripcion="Mayor almacenamiento y múltiples dispositivos",
        precio_mensual_ars=Decimal("45000"),
        visibilidad=VisibilidadPlan.PRIVADO,
        retencion_dias=30,
        granularidad_minutos=1,
        max_dispositivos=5,
        canales_notificacion=["email", "telegram", "whatsapp"],
    )

    response = use_case.crear_plan(dto)

    assert response.id
    assert response.nombre == "Profesional"
    assert response.retencion_dias == 30
    assert len(repo.planes) == 1
    assert repo.planes[0].id == response.id


def test_plan_mapper():
    plan = _plan_publico("plan-99")
    dto = PlanMapper.to_dto(plan)
    assert dto.id == "plan-99"
    assert dto.nombre == "Freemium Público"
    assert dto.precio_mensual_ars == Decimal("0")
    assert dto.visibilidad == VisibilidadPlan.PUBLICO

    create_dto = PlanCreateDTO(
        nombre="Test Plan",
        descripcion="Desc",
        precio_mensual_ars=Decimal("100"),
        visibilidad=VisibilidadPlan.PRIVADO,
        retencion_dias=15,
        granularidad_minutos=10,
        max_dispositivos=2,
        canales_notificacion=["email"],
    )
    entity = PlanMapper.create_dto_to_entity(create_dto, "custom-id")
    assert entity.id == "custom-id"
    assert entity.nombre == "Test Plan"
    assert entity.retencion_dias == 15
