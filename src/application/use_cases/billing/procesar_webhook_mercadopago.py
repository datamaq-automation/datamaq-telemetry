"""src/application/use_cases/billing/procesar_webhook_mercadopago.py."""

from dataclasses import dataclass

from src.application.use_cases.gestionar_suscripciones import GestionarSuscripcionesUseCase
from src.domain.billing.ports import ProveedorPagosPort, RegistroEventosWebhookPort

PROVEEDOR = "mercadopago"

_ESTADOS_ACTIVOS = {"authorized"}
_ESTADOS_DE_BAJA = {"cancelled", "paused"}


@dataclass
class ResultadoWebhook:
    procesado: bool
    accion: str  # "ignorado_duplicado" | "activado" | "cancelado" | "sin_cambios" | "referencia_invalida"


class ProcesarWebhookMercadoPagoUseCase:
    """Idempotente por `event_id` (ver `RegistroEventosWebhookPort`). La verificación de firma
    (`validar_firma_mp`) es responsabilidad del router, que rechaza antes de llegar acá."""

    def __init__(
        self,
        proveedor_pagos: ProveedorPagosPort,
        registro_eventos: RegistroEventosWebhookPort,
        gestionar_suscripciones: GestionarSuscripcionesUseCase,
    ) -> None:
        self.proveedor_pagos = proveedor_pagos
        self.registro_eventos = registro_eventos
        self.gestionar_suscripciones = gestionar_suscripciones

    def ejecutar(self, event_id: str, preapproval_id: str) -> ResultadoWebhook:
        if self.registro_eventos.ya_procesado(PROVEEDOR, event_id):
            return ResultadoWebhook(procesado=False, accion="ignorado_duplicado")

        info = self.proveedor_pagos.obtener_preapproval(preapproval_id)

        if not info.external_reference or ":" not in info.external_reference:
            self.registro_eventos.marcar_procesado(PROVEEDOR, event_id)
            return ResultadoWebhook(procesado=True, accion="referencia_invalida")

        organizacion_id, plan_id = info.external_reference.split(":", 1)

        if info.status in _ESTADOS_ACTIVOS and info.next_payment_date is not None:
            self.gestionar_suscripciones.activar_o_extender(organizacion_id, plan_id, info.next_payment_date)
            accion = "activado"
        elif info.status in _ESTADOS_DE_BAJA:
            self.gestionar_suscripciones.cancelar(organizacion_id)
            accion = "cancelado"
        else:
            accion = "sin_cambios"

        self.registro_eventos.marcar_procesado(PROVEEDOR, event_id)
        return ResultadoWebhook(procesado=True, accion=accion)
