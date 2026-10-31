"""src/application/use_cases/billing/generar_checkout_suscripcion.py."""

from src.domain.billing.entities import PreapprovalCreado
from src.domain.billing.exceptions import PayerEmailFaltanteError
from src.domain.billing.ports import ProveedorPagosPort
from src.domain.telemetria.exceptions import OrganizacionNoEncontradaError, PlanNoEncontradoError
from src.domain.telemetria.ports import RepositorioOrganizacionesPort, RepositorioPlanesPort


class GenerarCheckoutSuscripcionUseCase:
    """D1/D2 del plan de billing: el checkout es solo para organizaciones ya existentes
    (instaladas previamente), autenticadas — no da de alta clientes nuevos self-service."""

    def __init__(
        self,
        repo_planes: RepositorioPlanesPort,
        repo_organizaciones: RepositorioOrganizacionesPort,
        proveedor_pagos: ProveedorPagosPort,
        back_url: str,
    ) -> None:
        self.repo_planes = repo_planes
        self.repo_organizaciones = repo_organizaciones
        self.proveedor_pagos = proveedor_pagos
        self.back_url = back_url

    def ejecutar(self, organizacion_id: str, plan_id: str) -> PreapprovalCreado:
        org = self.repo_organizaciones.obtener_por_id(organizacion_id)
        if org is None:
            raise OrganizacionNoEncontradaError(f"Organización '{organizacion_id}' no existe.")

        # Cooperativas no tienen checkout (modelo sin cobro)
        if org.es_cooperativa:
            raise PayerEmailFaltanteError(
                f"La organización '{org.nombre}' es una cooperativa. "
                "Las cooperativas no participan del modelo de suscripción pagada."
            )

        plan = self.repo_planes.obtener_por_id(plan_id)
        if plan is None:
            raise PlanNoEncontradoError(f"Plan '{plan_id}' no existe en el catálogo.")

        if not org.email_contacto:
            raise PayerEmailFaltanteError(
                f"La organización '{org.nombre}' no tiene email_contacto configurado; "
                "Mercado Pago requiere un payer_email para crear la suscripción."
            )

        return self.proveedor_pagos.crear_preapproval(
            external_reference=f"{organizacion_id}:{plan_id}",
            monto_mensual_ars=plan.precio_mensual_ars,
            motivo=f"Suscripción DataMaq — Plan {plan.nombre}",
            payer_email=org.email_contacto,
            back_url=self.back_url,
        )
