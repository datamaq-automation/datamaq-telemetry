import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.infrastructure.fastapi.dependencies import (
    global_event_broadcaster,
    registrar_mqtt_listener,
    token_valido,
)
from src.infrastructure.fastapi.error_handler import manejar_404
from src.infrastructure.fastapi.middleware import RequestIdMiddleware
from src.infrastructure.fastapi.routes.alertas_router import (
    router as alertas_router,
)
from src.infrastructure.fastapi.routes.auth_router import (
    router as auth_router,
)
from src.infrastructure.fastapi.routes.dispositivos_router import (
    router as dispositivos_router,
)
from src.infrastructure.fastapi.routes.organizaciones_router import (
    router as organizaciones_router,
)
from src.infrastructure.fastapi.routes.planes_router import (
    router as planes_router,
)
from src.infrastructure.fastapi.routes.system_router import router as system_router
from src.infrastructure.fastapi.routes.telemetria_router import (
    router as telemetria_router,
)
from src.infrastructure.fastapi.security_headers import SecurityHeadersMiddleware
from src.infrastructure.paho_mqtt.mqtt_listener import MQTTListener
from src.infrastructure.settings.config import Settings, get_settings
from src.infrastructure.settings.logger import get_logger
from src.infrastructure.sqlalchemy.database import create_tables_if_needed

logger = get_logger("server")

active_websockets: list[WebSocket] = []
async_loop = None


async def manejar_excepcion_no_mapeada(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "excepcion_no_mapeada",
        exc_info=True,
        tipo=type(exc).__name__,
        metodo=request.method,
        ruta=request.url.path,
    )
    return JSONResponse(status_code=500, content={"detail": "error_interno"})


def websocket_broadcast_callback(topico: str, datos: dict):
    if not active_websockets or not async_loop:
        return
    msg = json.dumps({"topic": topico, "data": datos, "received_at": datetime.now(timezone.utc).isoformat()})
    for ws in list(active_websockets):
        try:
            asyncio.run_coroutine_threadsafe(ws.send_text(msg), async_loop)
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    global async_loop
    async_loop = asyncio.get_running_loop()

    create_tables_if_needed()
    logger.info("tablas_db_verificadas")

    # Hook up live WebSocket broadcasts
    global_event_broadcaster.suscribir(websocket_broadcast_callback)

    # Start MQTT background listener
    mqtt_listener = MQTTListener(publicador_eventos=global_event_broadcaster)
    registrar_mqtt_listener(mqtt_listener)
    mqtt_listener.start()

    logger.info("servidor_datamaq_listo", websockets_route="/ws/live", docs_route="/docs")

    yield

    # Clean shutdown
    logger.info("deteniendo_servidor_datamaq")
    mqtt_listener.stop()
    global_event_broadcaster.desuscribir(websocket_broadcast_callback)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="Datamaq Telemetry Platform API",
        description="Clean Architecture Backend para telemetría de medidores Powermeter",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.API_EXPOSE_DOCS else None,
        redoc_url="/redoc" if settings.API_EXPOSE_DOCS else None,
        openapi_url="/openapi.json" if settings.API_EXPOSE_DOCS else None,
    )

    if (settings.CORS_ORIGINS or "").strip() == "*":
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        origins = [o.strip() for o in (settings.CORS_ORIGINS or "").split(",") if o.strip()]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(Exception, manejar_excepcion_no_mapeada)
    app.add_exception_handler(StarletteHTTPException, manejar_404)

    # Register Routers
    app.include_router(system_router)
    app.include_router(telemetria_router)
    app.include_router(dispositivos_router)
    app.include_router(organizaciones_router)
    app.include_router(planes_router)
    app.include_router(alertas_router)
    app.include_router(auth_router)

    # WebSockets Live Telemetry Stream
    @app.websocket("/ws/live")
    async def websocket_stream(websocket: WebSocket):
        if settings.AUTH_REQUIRED:
            cookie_token = websocket.cookies.get(settings.AUTH_COOKIE_NOMBRE)
            auth_header = websocket.headers.get("authorization")
            if not token_valido(cookie_token, auth_header, settings.API_SECRET_KEY, settings.API_SECRET_KEY_ANTERIOR):
                await websocket.close(code=1008)
                return
        await websocket.accept()
        active_websockets.append(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            if websocket in active_websockets:
                active_websockets.remove(websocket)

    return app
