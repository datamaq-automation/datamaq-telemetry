import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from src.infrastructure.fastapi.dependencies import global_event_broadcaster
from src.infrastructure.fastapi.routes.alertas_router import (
    router as alertas_router,
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
from src.infrastructure.paho_mqtt.mqtt_listener import MQTTListener
from src.infrastructure.settings.config import get_settings
from src.infrastructure.settings.logger import get_logger
from src.infrastructure.sqlalchemy.database import create_tables_if_needed

logger = get_logger("server")

active_websockets: list[WebSocket] = []
async_loop = None


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
    mqtt_listener.start()

    logger.info("servidor_datamaq_listo", websockets_route="/ws/live", docs_route="/docs")

    yield

    # Clean shutdown
    logger.info("deteniendo_servidor_datamaq")
    mqtt_listener.stop()
    global_event_broadcaster.desuscribir(websocket_broadcast_callback)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Datamaq Telemetry Platform API",
        description="Clean Architecture Backend para telemetría de medidores Powermeter",
        version="1.0.0",
        lifespan=lifespan,
    )

    settings = get_settings()
    if settings.CORS_ORIGINS.strip() == "*":
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Register Routers
    app.include_router(system_router)
    app.include_router(telemetria_router)
    app.include_router(dispositivos_router)
    app.include_router(organizaciones_router)
    app.include_router(planes_router)
    app.include_router(alertas_router)

    # WebSockets Live Telemetry Stream
    @app.websocket("/ws/live")
    async def websocket_stream(websocket: WebSocket):
        await websocket.accept()
        active_websockets.append(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            if websocket in active_websockets:
                active_websockets.remove(websocket)

    return app
