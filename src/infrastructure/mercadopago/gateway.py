"""src/infrastructure/mercadopago/gateway.py.

Adaptador HTTP hacia la API de Mercado Pago (suscripciones recurrentes / `preapproval`).
Referencia: https://www.mercadopago.com.ar/developers/es/reference/subscriptions/_preapproval/post

NOTA para cuando haya credenciales reales de sandbox: la forma exacta del JSON de
respuesta de GET /preapproval/{id} se validó contra la documentación pública, no contra
una llamada real — `_extraer_next_payment_date` prueba las dos ubicaciones documentadas
(top-level y dentro de `auto_recurring`) mirando cuál trae valor, pero conviene confirmar
con una respuesta real antes de depender de esto en producción.
"""

from datetime import datetime
from decimal import Decimal

import httpx

from src.domain.billing.entities import PreapprovalCreado, PreapprovalInfo
from src.domain.billing.ports import ProveedorPagosPort


class MercadoPagoGateway(ProveedorPagosPort):
    def __init__(
        self, access_token: str, base_url: str = "https://api.mercadopago.com", client: httpx.Client | None = None
    ):
        self._auth_header = {"Authorization": f"Bearer {access_token}"}
        self._client = client or httpx.Client(base_url=base_url, timeout=15.0)

    def crear_preapproval(
        self,
        external_reference: str,
        monto_mensual_ars: Decimal,
        motivo: str,
        payer_email: str,
        back_url: str,
    ) -> PreapprovalCreado:
        respuesta = self._client.post(
            "/preapproval",
            headers=self._auth_header,
            json={
                "reason": motivo,
                "external_reference": external_reference,
                "payer_email": payer_email,
                "back_url": back_url,
                "auto_recurring": {
                    "frequency": 1,
                    "frequency_type": "months",
                    "transaction_amount": float(monto_mensual_ars),
                    "currency_id": "ARS",
                },
            },
        )
        respuesta.raise_for_status()
        data = respuesta.json()
        init_point = data.get("init_point") or data.get("sandbox_init_point")
        return PreapprovalCreado(id=data["id"], init_point=init_point)

    def obtener_preapproval(self, preapproval_id: str) -> PreapprovalInfo:
        respuesta = self._client.get(f"/preapproval/{preapproval_id}", headers=self._auth_header)
        respuesta.raise_for_status()
        data = respuesta.json()
        return PreapprovalInfo(
            id=data["id"],
            status=data.get("status", ""),
            external_reference=data.get("external_reference"),
            next_payment_date=self._extraer_next_payment_date(data),
        )

    @staticmethod
    def _extraer_next_payment_date(data: dict) -> datetime | None:
        crudo = data.get("next_payment_date") or (data.get("auto_recurring") or {}).get("next_payment_date")
        if not crudo:
            return None
        return datetime.fromisoformat(crudo.replace("Z", "+00:00"))
