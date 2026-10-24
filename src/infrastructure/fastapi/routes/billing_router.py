"""src/infrastructure/fastapi/routes/billing_router.py."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from src.application.use_cases.billing.generar_checkout_suscripcion import (
    GenerarCheckoutSuscripcionUseCase,
)
from src.application.use_cases.billing.procesar_webhook_mercadopago import (
    ProcesarWebhookMercadoPagoUseCase,
)
from src.domain.billing.servicios.validador_firma_mp import FirmaWebhookInvalidaError, validar_firma_mp
from src.infrastructure.fastapi.dependencies import requiere_rol_admin
from src.infrastructure.fastapi.dependencies_billing import (
    get_generar_checkout_use_case,
    get_procesar_webhook_mercadopago_use_case,
)
from src.infrastructure.fastapi.error_handler import manejar_error_http
from src.infrastructure.settings.config import get_settings
from src.infrastructure.settings.logger import get_logger

logger = get_logger("billing")

router = APIRouter(prefix="/api/v1", tags=["Billing"])


class CheckoutRequestDTO(BaseModel):
    plan_id: str


class CheckoutResponseDTO(BaseModel):
    preapproval_id: str
    init_point: str


@router.post("/suscripciones/checkout", response_model=CheckoutResponseDTO)
def crear_checkout_suscripcion(
    dto: CheckoutRequestDTO,
    claims: Annotated[dict[str, Any], Depends(requiere_rol_admin)],
    use_case: Annotated[GenerarCheckoutSuscripcionUseCase, Depends(get_generar_checkout_use_case)],
):
    """D1/D2 del plan de billing: solo para la organización del usuario autenticado
    (ya instalada) — no da de alta organizaciones nuevas."""
    settings = get_settings()
    if not settings.BILLING_HABILITADO:
        raise HTTPException(status_code=503, detail="El servicio de billing está deshabilitado.")
    organizacion_id = claims.get("org")
    if not organizacion_id:
        raise HTTPException(status_code=422, detail="El usuario autenticado no tiene organización asociada.")
    try:
        creado = use_case.ejecutar(organizacion_id, dto.plan_id)
    except Exception as e:
        manejar_error_http(e)
    return CheckoutResponseDTO(preapproval_id=creado.id, init_point=creado.init_point)


@router.post("/webhooks/mercadopago", status_code=200)
async def webhook_mercadopago(
    request: Request,
    use_case: Annotated[ProcesarWebhookMercadoPagoUseCase, Depends(get_procesar_webhook_mercadopago_use_case)],
    x_signature: Annotated[str | None, Header()] = None,
    x_request_id: Annotated[str | None, Header()] = None,
):
    """Sin autenticación de usuario (lo llama Mercado Pago, no un cliente nuestro) — la
    verificación de identidad es la firma HMAC de `x-signature`, no un JWT."""
    settings = get_settings()
    if not settings.BILLING_HABILITADO:
        raise HTTPException(status_code=503, detail="El servicio de billing está deshabilitado.")
    data_id = request.query_params.get("data.id") or request.query_params.get("id")
    if not data_id:
        raise HTTPException(status_code=400, detail="Falta data.id en la notificación.")
    if not x_signature or not x_request_id:
        # Mercado Pago reintenta por código de estado, no por el texto: el detalle de qué header falta va al log.
        logger.warning(
            "webhook_mp_sin_firma",
            falta_x_signature=not x_signature,
            falta_x_request_id=not x_request_id,
        )
        raise HTTPException(status_code=400, detail="Solicitud sin firma válida.")
    if not settings.mp_webhook_secret_configurado:
        # Sin secreto, validar_firma_mp aceptaría una firma hecha con clave vacía. Se corta antes de verificar.
        # El nombre de la variable va al log, no a la respuesta.
        logger.error("webhook_mp_secreto_ausente", variable="MP_WEBHOOK_SECRET")
        raise HTTPException(status_code=503, detail="El servicio de pagos no está disponible.")

    try:
        validar_firma_mp(x_signature, x_request_id, data_id, settings.MP_WEBHOOK_SECRET)
    except FirmaWebhookInvalidaError:
        raise HTTPException(status_code=401, detail="Firma inválida.") from None

    event_id = request.query_params.get("id") or data_id
    try:
        resultado = use_case.ejecutar(event_id=event_id, preapproval_id=data_id)
    except Exception as e:
        manejar_error_http(e)
    return {"accion": resultado.accion}
