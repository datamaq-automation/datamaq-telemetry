"""tests/unit/test_generar_checkout_suscripcion.py."""

from decimal import Decimal

import pytest

from src.application.use_cases.billing.generar_checkout_suscripcion import (
    GenerarCheckoutSuscripcionUseCase,
)
from src.domain.billing.entities import PreapprovalCreado, PreapprovalInfo
from src.domain.billing.exceptions import PayerEmailFaltanteError
from src.domain.billing.ports import ProveedorPagosPort
from src.domain.telemetria.entities import Organizacion, PlanTelemetria
from src.domain.telemetria.exceptions import OrganizacionNoEncontradaError, PlanNoEncontradoError
from src.domain.telemetria.value_objects import VisibilidadPlan


class FakeProveedorPagos(ProveedorPagosPort):
    def __init__(self):
        self.llamadas_crear: list[dict] = []

    def crear_preapproval(self, external_reference, monto_mensual_ars, motivo, payer_email, back_url):
        self.llamadas_crear.append(
            {
                "external_reference": external_reference,
                "monto_mensual_ars": monto_mensual_ars,
                "motivo": motivo,
                "payer_email": payer_email,
                "back_url": back_url,
            }
        )
        return PreapprovalCreado(id="preap-1", init_point="https://mp.example/checkout/preap-1")

    def obtener_preapproval(self, preapproval_id):
        return PreapprovalInfo(id=preapproval_id, status="authorized", external_reference=None, next_payment_date=None)


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
    def __init__(self, orgs: dict[str, Organizacion]):
        self.orgs = orgs

    def obtener_por_id(self, organizacion_id):
        return self.orgs.get(organizacion_id)

    def listar_organizaciones(self):
        return list(self.orgs.values())

    def guardar_organizacion(self, org):
        self.orgs[org.id] = org
        return org

    def obtener_planta_por_id(self, planta_id):
        return None

    def listar_plantas(self, organizacion_id=None):
        return []

    def obtener_nodos_unifilar(self, planta_id):
        return []

    def obtener_zonas_planta(self, planta_id):
        return []

    def obtener_dispositivos_layout(self, planta_id):
        return []

    def obtener_instalacion_medidor(self, dispositivo_id):
        return None


def _plan() -> PlanTelemetria:
    return PlanTelemetria(
        id="plan-pro",
        nombre="PRO",
        descripcion="Plan PRO",
        precio_mensual_ars=Decimal("5000"),
        visibilidad=VisibilidadPlan.PUBLICO,
        retencion_dias=365,
        granularidad_minutos=1,
        max_dispositivos=10,
        canales_notificacion=["email"],
    )


def test_ejecutar_ok_llama_al_proveedor_con_los_datos_correctos():
    plan = _plan()
    org = Organizacion(id="org-1", nombre="Cliente Uno", email_contacto="cliente@example.com")
    proveedor = FakeProveedorPagos()
    uc = GenerarCheckoutSuscripcionUseCase(
        FakeRepoPlanes({plan.id: plan}), FakeRepoOrganizaciones({org.id: org}), proveedor, "https://back.example"
    )

    resultado = uc.ejecutar("org-1", "plan-pro")

    assert resultado.init_point == "https://mp.example/checkout/preap-1"
    assert proveedor.llamadas_crear[0]["external_reference"] == "org-1:plan-pro"
    assert proveedor.llamadas_crear[0]["payer_email"] == "cliente@example.com"
    assert proveedor.llamadas_crear[0]["monto_mensual_ars"] == Decimal("5000")


def test_plan_inexistente_falla():
    org = Organizacion(id="org-1", nombre="Cliente Uno", email_contacto="cliente@example.com")
    uc = GenerarCheckoutSuscripcionUseCase(
        FakeRepoPlanes({}), FakeRepoOrganizaciones({org.id: org}), FakeProveedorPagos(), "https://back.example"
    )
    with pytest.raises(PlanNoEncontradoError):
        uc.ejecutar("org-1", "plan-fantasma")


def test_organizacion_inexistente_falla():
    plan = _plan()
    uc = GenerarCheckoutSuscripcionUseCase(
        FakeRepoPlanes({plan.id: plan}), FakeRepoOrganizaciones({}), FakeProveedorPagos(), "https://back.example"
    )
    with pytest.raises(OrganizacionNoEncontradaError):
        uc.ejecutar("org-fantasma", "plan-pro")


def test_organizacion_sin_email_contacto_falla():
    plan = _plan()
    org = Organizacion(id="org-1", nombre="Cliente Uno", email_contacto=None)
    uc = GenerarCheckoutSuscripcionUseCase(
        FakeRepoPlanes({plan.id: plan}),
        FakeRepoOrganizaciones({org.id: org}),
        FakeProveedorPagos(),
        "https://back.example",
    )
    with pytest.raises(PayerEmailFaltanteError):
        uc.ejecutar("org-1", "plan-pro")
