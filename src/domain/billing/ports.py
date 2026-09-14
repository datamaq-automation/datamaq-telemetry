"""src/domain/billing/ports.py."""

from abc import ABC, abstractmethod
from decimal import Decimal

from src.domain.billing.entities import PreapprovalCreado, PreapprovalInfo


class ProveedorPagosPort(ABC):
    """Puerto hacia el proveedor de pagos (Mercado Pago). El dominio no conoce HTTP ni
    el formato de ninguna API externa — solo estos dos verbos."""

    @abstractmethod
    def crear_preapproval(
        self,
        external_reference: str,
        monto_mensual_ars: Decimal,
        motivo: str,
        payer_email: str,
        back_url: str,
    ) -> PreapprovalCreado:
        pass

    @abstractmethod
    def obtener_preapproval(self, preapproval_id: str) -> PreapprovalInfo:
        pass


class RegistroEventosWebhookPort(ABC):
    """Idempotencia de webhooks: un mismo evento reenviado por el proveedor no debe
    procesarse dos veces."""

    @abstractmethod
    def ya_procesado(self, proveedor: str, event_id: str) -> bool:
        pass

    @abstractmethod
    def marcar_procesado(self, proveedor: str, event_id: str) -> None:
        pass
