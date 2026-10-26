"""src/infrastructure/fastapi/dependencies_billing.py.

Separado de `dependencies.py` (no por capa, sino porque ese archivo ya está en el
límite de tamaño del baseline de `scripts/verify_code_size.py`)."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from src.application.use_cases.billing.generar_checkout_suscripcion import (
    GenerarCheckoutSuscripcionUseCase,
)
from src.application.use_cases.billing.procesar_webhook_mercadopago import (
    ProcesarWebhookMercadoPagoUseCase,
)
from src.application.use_cases.gestionar_suscripciones import GestionarSuscripcionesUseCase
from src.infrastructure.mercadopago.gateway import MercadoPagoGateway
from src.infrastructure.settings.config import get_settings
from src.infrastructure.sqlalchemy.database import get_db_session
from src.infrastructure.sqlalchemy.mysql_repositories import (
    MySQLPlanesRepository,
    MySQLRegistroEventosWebhook,
    MySQLSuscripcionesRepository,
)
from src.infrastructure.yaml.repositories.organizaciones_repository import YamlOrganizacionesRepository


def get_mercadopago_gateway() -> MercadoPagoGateway:
    settings = get_settings()
    return MercadoPagoGateway(settings.MP_ACCESS_TOKEN, base_url=settings.MP_BASE_URL)


def get_generar_checkout_use_case(
    db: Annotated[Session, Depends(get_db_session)],
    proveedor_pagos: Annotated[MercadoPagoGateway, Depends(get_mercadopago_gateway)],
) -> GenerarCheckoutSuscripcionUseCase:
    settings = get_settings()
    return GenerarCheckoutSuscripcionUseCase(
        MySQLPlanesRepository(db),
        YamlOrganizacionesRepository(),
        proveedor_pagos,
        back_url=settings.MP_BACK_URL_EXITO,
    )


def get_procesar_webhook_mercadopago_use_case(
    db: Annotated[Session, Depends(get_db_session)],
    proveedor_pagos: Annotated[MercadoPagoGateway, Depends(get_mercadopago_gateway)],
) -> ProcesarWebhookMercadoPagoUseCase:
    return ProcesarWebhookMercadoPagoUseCase(
        proveedor_pagos,
        MySQLRegistroEventosWebhook(db),
        GestionarSuscripcionesUseCase(MySQLSuscripcionesRepository(db), MySQLPlanesRepository(db)),
    )
