"""src/domain/billing/entities.py."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class PreapprovalCreado:
    """Resultado de dar de alta una suscripción recurrente en el proveedor de pagos."""

    id: str
    init_point: str


@dataclass
class PreapprovalInfo:
    """Estado de una suscripción recurrente ya existente en el proveedor de pagos.

    `next_payment_date` es la fecha del próximo cobro que el proveedor va a intentar;
    cuando `status == "authorized"` la usamos directamente como `pro_vence_en` — si el
    próximo cobro falla, el vencimiento ya reflejado hace su trabajo sin lógica extra.
    """

    id: str
    status: str
    external_reference: str | None
    next_payment_date: datetime | None
