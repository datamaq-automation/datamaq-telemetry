"""src/infrastructure/fastapi/server.py."""

import asyncio
import json
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.adapters.gateways.mqtt_comando_rafaga import MqttComandoRafagaGateway
from src.application.use_cases.caracterizar_carga import CaracterizarCargaUseCase
from src.application.use_cases.ingesta.registro_campanas import registro_campanas_activas
from src.application.use_cases.ingesta.resolvedor_dispositivo import ResolvedorDispositivoIngesta
from src.application.use_cases.renovar_tiempo_real_medidores import RenovarTiempoRealMedidoresUseCase
from src.domain.telemetria.services import debe_recibir_evento
from src.domain.telemetria.servicios.alcance_tiempo_real import alcance_de_clientes
from src.domain.telemetria.value_objects import MacAddress
from src.infrastructure.auth.jwt_token_service import JwtTokenService
from src.infrastructure.fastapi.auth_cookies import ORIGENES_CORS_CYBERSYN
from src.infrastructure.fastapi.dependencies import (
    extraer_token,
    get_mqtt_listener,
    global_event_broadcaster,
    global_telemetria_buffer,
    registrar_mqtt_listener,
)
from src.infrastructure.fastapi.error_handler import manejar_404
from src.infrastructure.fastapi.headers_historico import HEADER_DATOS_DESDE, HEADER_POTENCIA_REFERENCIA
from src.infrastructure.fastapi.middleware import RequestIdMiddleware
from src.infrastructure.fastapi.routes.admin_router import router as admin_router
from src.infrastructure.fastapi.routes.alertas_router import router as alertas_router
from src.infrastructure.fastapi.routes.analitica_router import router as analitica_router
from src.infrastructure.fastapi.routes.asistente_router import router as asistente_router
from src.infrastructure.fastapi.routes.audit_router import router as audit_router
from src.infrastructure.fastapi.routes.auth_router import router as auth_router
from src.infrastructure.fastapi.routes.billing_router import router as billing_router
from src.infrastructure.fastapi.routes.cargas_router import router as cargas_router
from src.infrastructure.fastapi.routes.disponibilidad_router import router as disponibilidad_router
from src.infrastructure.fastapi.routes.dispositivos_router import router as dispositivos_router
from src.infrastructure.fastapi.routes.maquinas_router import router as maquinas_router
from src.infrastructure.fastapi.routes.notificador_router import router as notificador_router
from src.infrastructure.fastapi.routes.oauth_router import router as oauth_router
from src.infrastructure.fastapi.routes.organizaciones_router import router as organizaciones_router
from src.infrastructure.fastapi.routes.planes_router import router as planes_router
from src.infrastructure.fastapi.routes.planta_estructura_router import router as planta_estructura_router
from src.infrastructure.fastapi.routes.produccion_router import router as produccion_router
from src.infrastructure.fastapi.routes.sge_router import router as sge_router
from src.infrastructure.fastapi.routes.system_router import router as system_router
from src.infrastructure.fastapi.routes.telemetria_router import router as telemetria_router
from src.infrastructure.fastapi.routes.usuarios_router import router as usuarios_router
from src.infrastructure.fastapi.security_headers import SecurityHeadersMiddleware
from src.infrastructure.paho_mqtt.mqtt_listener import MQTTListener
from src.infrastructure.settings.config import Settings, get_settings
from src.infrastructure.settings.logger import get_logger
from src.infrastructure.sqlalchemy.database import (
    create_tables_if_needed,
    get_session_factory,
    verificar_estado_migraciones,
)
from src.infrastructure.sqlalchemy.mysql_repositories import (
    MySQLCampanasRepository,
    MySQLCargasRepository,
    MySQLDispositivosRepository,
)
from src.infrastructure.yaml.repositories.organizaciones_repository import YamlOrganizacionesRepository
from tools.mcp.server import mcp as datamaq_mcp

mcp_app = datamaq_mcp.streamable_http_app()

logger = get_logger("server")


@dataclass
class ConnectedClient:
    """Cliente WebSocket conectado a /ws/live, con el contexto de organización de su token.

    `organizacion_id` es None para superadmin (ve todo) o cuando el usuario no tiene
    organización asociada (en ese caso, `es_superadmin` decide si ve algo: ver
    `debe_recibir_evento`).
    """

    websocket: WebSocket
    organizacion_id: str | None
    es_superadmin: bool


active_websockets: list[ConnectedClient] = []
async_loop = None

# Código de cierre de aplicación que distingue "token inválido" en /ws/live.
# Se emite tras `accept()` para que el navegador pueda leerlo (evita el 1006 opaco).
WS_CLOSE_TOKEN_INVALIDO = 4401


async def manejar_excepcion_no_mapeada(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None) or structlog.contextvars.get_contextvars().get("request_id")
    contexto: dict[str, Any] = {
        "tipo": type(exc).__name__,
        "metodo": request.method,
        "ruta": request.url.path,
        "request_id": request_id,
    }
    orig = getattr(exc, "orig", None)
    if orig is not None:
        contexto["db_error"] = str(orig)
    statement = getattr(exc, "statement", None)
    if statement is not None:
        contexto["db_statement"] = str(statement)

    logger.error("excepcion_no_mapeada", exc_info=True, **contexto)
    headers = {"X-Request-ID": request_id} if request_id else None
    return JSONResponse(status_code=500, content={"detail": "error_interno"}, headers=headers)


class WebSocketMetrics:
    def __init__(self) -> None:
        self.total_conexiones: int = 0
        self.total_desconexiones: int = 0
        self.total_broadcasts: int = 0
        self.ultimo_broadcast_en: str | None = None
        self.ultimo_topico: str | None = None
        self.ultimo_payload_bytes: int = 0
        self.total_mensajes_enviados_ok: int = 0
        self.total_mensajes_fallidos: int = 0

    def to_dict(self, clientes_activos: int) -> dict[str, Any]:
        return {
            "clientes_activos": clientes_activos,
            "total_conexiones": self.total_conexiones,
            "total_desconexiones": self.total_desconexiones,
            "total_broadcasts": self.total_broadcasts,
            "ultimo_broadcast_en": self.ultimo_broadcast_en,
            "ultimo_topico": self.ultimo_topico,
            "ultimo_payload_bytes": self.ultimo_payload_bytes,
            "total_mensajes_enviados_ok": self.total_mensajes_enviados_ok,
            "total_mensajes_fallidos": self.total_mensajes_fallidos,
        }


ws_metrics = WebSocketMetrics()


def obtener_metricas_ws() -> dict[str, Any]:
    return ws_metrics.to_dict(len(active_websockets))


def _resolver_organizacion_evento(topico: str) -> str | None:
    """Resuelve la organizacion_id del dispositivo que originó `topico` (formato `.../{mac}/{subtopico}`).

    Usa la caché en memoria de `ResolvedorDispositivoIngesta` (poblada por el worker de ingesta,
    mismo proceso) y solo abre una sesión de DB en el cache-miss de planta->organización.
    Cualquier fallo se trata como "sin organización resuelta" (fail-closed: solo superadmin la ve).
    """
    try:
        partes = topico.split("/")
        if len(partes) < 3:
            return None
        mac_raw = partes[2]
        mac_vo = MacAddress(mac_raw)
        dispositivo = ResolvedorDispositivoIngesta._device_cache.get(mac_vo.valor)
        if dispositivo is None or not dispositivo.planta_id:
            return None
        planta_id = dispositivo.planta_id
        if planta_id in ResolvedorDispositivoIngesta._organizacion_cache:
            return ResolvedorDispositivoIngesta._organizacion_cache[planta_id]

        session_factory = get_session_factory()
        db = session_factory()
        try:
            repo = YamlOrganizacionesRepository()
            return ResolvedorDispositivoIngesta.resolver_organizacion_id(mac_raw, repo)
        finally:
            db.close()
    except Exception as exc:
        logger.warning("resolver_organizacion_evento_fallido", topico=topico, error=str(exc))
        return None


def websocket_broadcast_callback(topico: str, datos: dict):
    recibido_en = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    msg = json.dumps({"topic": topico, "data": datos, "received_at": recibido_en})
    msg_bytes = len(msg)

    total_clientes = len(active_websockets)
    if total_clientes == 0:
        logger.info("ws_broadcast_sin_clientes", topico=topico, bytes=msg_bytes)
        ws_metrics.total_broadcasts += 1
        ws_metrics.ultimo_broadcast_en = recibido_en
        ws_metrics.ultimo_topico = topico
        ws_metrics.ultimo_payload_bytes = msg_bytes
        return

    if not async_loop:
        logger.warning("ws_broadcast_sin_loop", topico=topico)
        return

    organizacion_evento = _resolver_organizacion_evento(topico)

    enviados_ok = 0
    fallidos = 0
    omitidos_aislamiento = 0
    for cliente in list(active_websockets):
        if not debe_recibir_evento(cliente.es_superadmin, cliente.organizacion_id, organizacion_evento):
            omitidos_aislamiento += 1
            continue
        try:
            asyncio.run_coroutine_threadsafe(cliente.websocket.send_text(msg), async_loop)
            enviados_ok += 1
        except Exception as exc:
            fallidos += 1
            logger.warning("ws_broadcast_error_cliente", error=str(exc), topico=topico)
            if cliente in active_websockets:
                active_websockets.remove(cliente)

    ws_metrics.total_broadcasts += 1
    ws_metrics.ultimo_broadcast_en = recibido_en
    ws_metrics.ultimo_topico = topico
    ws_metrics.ultimo_payload_bytes = msg_bytes
    ws_metrics.total_mensajes_enviados_ok += enviados_ok
    ws_metrics.total_mensajes_fallidos += fallidos

    logger.info(
        "ws_broadcast_despachado",
        topico=topico,
        bytes=msg_bytes,
        clientes_activos=total_clientes,
        enviados_ok=enviados_ok,
        fallidos=fallidos,
        omitidos_aislamiento=omitidos_aislamiento,
    )


def _renovar_modo_tiempo_real_medidores(listener: Any, clientes: list[ConnectedClient]) -> None:
    """Renueva el tiempo real solo de los medidores que algún cliente de `clientes` puede ver (#15)."""
    alcance = alcance_de_clientes((c.es_superadmin, c.organizacion_id) for c in clientes)
    if alcance.vacio:
        return
    try:
        db = get_session_factory()()
        try:
            use_case = RenovarTiempoRealMedidoresUseCase(
                MySQLDispositivosRepository(db), MqttComandoRafagaGateway(listener)
            )
            resultado = use_case.ejecutar(alcance, datetime.now(timezone.utc))
            logger.info(
                "realtime_mode_auto_renovado",
                total_dispositivos=resultado.renovados,
                omitidos_sin_recepcion_reciente=resultado.omitidos_sin_recepcion_reciente,
                organizaciones="todas" if alcance.todas else sorted(alcance.organizaciones),
            )
        finally:
            db.close()
    except Exception as e:
        logger.warning("realtime_mode_auto_renovacion_fallida", error=str(e))


INTERVALO_SOSTEN_CAMPANAS_S = 45.0
"""Menor que los 120 s de duración de la ráfaga, con margen para un reintento perdido."""


def _sostener_campanas() -> tuple[int, int]:
    """Renueva la ráfaga de las campañas vivas y cierra las vencidas.

    Corre con su propia sesión de base y en un hilo aparte porque `CaracterizarCargaUseCase`
    es síncrono; el bucle que lo invoca vive en el event loop y no debe bloquearse.
    """
    session_factory = get_session_factory()
    db = session_factory()
    try:
        use_case = CaracterizarCargaUseCase(
            repo_campanas=MySQLCampanasRepository(db),
            repo_cargas=MySQLCargasRepository(db),
            repo_dispositivos=MySQLDispositivosRepository(db),
            registro=registro_campanas_activas,
            comando_rafaga=MqttComandoRafagaGateway(get_mqtt_listener()),
        )
        return use_case.sostener_campanas_activas()
    finally:
        db.close()


async def _loop_campanas_activas() -> None:
    """Mantiene vivas las campañas de caracterización.

    Independiente de `_ws_heartbeat_loop`, que solo renueva la ráfaga mientras haya un
    navegador conectado: una campaña puede correr de madrugada sin nadie mirando, y en
    ese caso este bucle es lo único que impide que el medidor vuelva a 5 minutos en
    medio de la medición.

    También cierra las campañas vencidas, para que una olvidada no deje al medidor
    publicando en ráfaga y escribiendo muestras indefinidamente.
    """
    while True:
        try:
            await asyncio.sleep(INTERVALO_SOSTEN_CAMPANAS_S)
            # Se consulta la base aunque el registro en memoria esté vacío: tras un
            # reinicio del servicio arranca vacío y las campañas siguen vivas en la tabla.
            renovadas, cerradas = await asyncio.to_thread(_sostener_campanas)
            if renovadas or cerradas:
                logger.info("campanas_sostenidas", renovadas=renovadas, cerradas=cerradas)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("campanas_sosten_fallido", error=str(e))


async def _ws_heartbeat_loop() -> None:
    """Mantiene activa la conexión a través de Cloudflare o Nginx ante períodos de inactividad
    y renueva el modo de tiempo real en medidores mientras haya clientes WebSocket conectados."""
    ultimo_sync_realtime: float = 0.0
    while True:
        try:
            await asyncio.sleep(25)
            if active_websockets:
                ahora = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                ping_msg = json.dumps({"topic": "system/heartbeat", "data": {"status": "ok"}, "received_at": ahora})
                for cliente in list(active_websockets):
                    try:
                        await cliente.websocket.send_text(ping_msg)
                    except Exception:
                        if cliente in active_websockets:
                            active_websockets.remove(cliente)

                # Renovación periódica de sampleo rápido (cada 60 segundos si hay clientes activos)
                ahora_ts = time.time()
                if ahora_ts - ultimo_sync_realtime >= 60.0:
                    ultimo_sync_realtime = ahora_ts
                    listener = get_mqtt_listener()
                    if listener and listener.esta_conectado():
                        _renovar_modo_tiempo_real_medidores(listener, list(active_websockets))
        except asyncio.CancelledError:
            break
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    global async_loop
    async_loop = asyncio.get_running_loop()

    create_tables_if_needed()
    verificar_estado_migraciones()
    logger.info("tablas_db_verificadas")

    try:
        from src.infrastructure.sqlalchemy.verificador_consistencia import verificar_consistencia_organizaciones

        db_session = get_session_factory()()
        try:
            verificar_consistencia_organizaciones(db_session)
        finally:
            db_session.close()
    except Exception as e:
        logger.warning("verificacion_consistencia_fallida", error=str(e))

    from src.infrastructure.fastapi.startup_verificaciones import ejecutar_verificaciones_yaml

    ejecutar_verificaciones_yaml()

    # Hook up live WebSocket broadcasts
    global_event_broadcaster.suscribir(websocket_broadcast_callback)
    # Buffer en RAM de lecturas en vivo por dispositivo (sobrevive a un F5 del navegador)
    global_event_broadcaster.suscribir(global_telemetria_buffer.agregar)

    # Start MQTT background listener
    mqtt_listener = MQTTListener(publicador_eventos=global_event_broadcaster)
    registrar_mqtt_listener(mqtt_listener)
    mqtt_listener.start()

    # Iniciar heartbeat para Cloudflare / proxies
    heartbeat_task = asyncio.create_task(_ws_heartbeat_loop())
    campanas_task = asyncio.create_task(_loop_campanas_activas())

    logger.info("servidor_datamaq_listo", websockets_route="/ws/live", docs_route="/docs")

    try:
        async with mcp_app.router.lifespan_context(mcp_app):
            yield
    finally:
        if hasattr(datamaq_mcp, "_session_manager") and datamaq_mcp._session_manager is not None:
            datamaq_mcp._session_manager._has_started = False

    # Clean shutdown
    logger.info("deteniendo_servidor_datamaq")
    heartbeat_task.cancel()
    campanas_task.cancel()
    for tarea in (heartbeat_task, campanas_task):
        try:
            await tarea
        except asyncio.CancelledError:
            pass
    mqtt_listener.stop()
    global_event_broadcaster.desuscribir(websocket_broadcast_callback)
    global_event_broadcaster.desuscribir(global_telemetria_buffer.agregar)


async def _autenticar_cliente_ws(websocket: WebSocket, settings: Settings, client_host: str) -> ConnectedClient | None:
    """Valida el token (si aplica) y arma el `ConnectedClient` con su contexto de organización.

    Devuelve None (y ya cerró la conexión) si el token es inválido/falta con AUTH_REQUIRED activo.
    """
    if not settings.AUTH_REQUIRED:
        return ConnectedClient(websocket=websocket, organizacion_id=None, es_superadmin=True)

    cookie_token = websocket.cookies.get(settings.AUTH_COOKIE_NOMBRE)
    auth_header = websocket.headers.get("authorization")
    token = extraer_token(cookie_token, auth_header)
    adicionales = [settings.API_SECRET_KEY_ANTERIOR] if settings.API_SECRET_KEY_ANTERIOR else None
    claims = JwtTokenService(settings.API_SECRET_KEY).verificar(token, adicionales) if token else None
    if claims is None:
        logger.warning("ws_auth_rechazada", client=client_host, razon="token_invalido")
        await websocket.close(code=WS_CLOSE_TOKEN_INVALIDO, reason="token_invalido")
        return None

    es_superadmin = claims.get("rol") in ("superadmin", "invitado_global")
    organizacion_id = None if es_superadmin else claims.get("org")
    return ConnectedClient(websocket=websocket, organizacion_id=organizacion_id, es_superadmin=es_superadmin)


def _registrar_cliente_ws(cliente: ConnectedClient, client_host: str) -> None:
    alcance_previo = alcance_de_clientes((c.es_superadmin, c.organizacion_id) for c in active_websockets)
    active_websockets.append(cliente)
    ws_metrics.total_conexiones += 1
    logger.info(
        "ws_cliente_conectado",
        client=client_host,
        total_activos=len(active_websockets),
        organizacion_id=cliente.organizacion_id,
        es_superadmin=cliente.es_superadmin,
    )
    # Sin esperar al heartbeat (hasta ~85 s) si el cliente nuevo mira medidores que nadie estaba mirando.
    if not alcance_previo.cubre(alcance_de_clientes([(cliente.es_superadmin, cliente.organizacion_id)])):
        listener = get_mqtt_listener()
        if listener and listener.esta_conectado():
            _renovar_modo_tiempo_real_medidores(listener, [cliente])


async def _bucle_recepcion_ws(websocket: WebSocket) -> None:
    while True:
        data = await websocket.receive_text()
        if data in ("ping", '{"type":"ping"}'):
            await websocket.send_text(json.dumps({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()}))


def _desconectar_cliente_ws(cliente: ConnectedClient, client_host: str, evento: str, **detalle: Any) -> None:
    if cliente in active_websockets:
        active_websockets.remove(cliente)
    ws_metrics.total_desconexiones += 1
    log_fn = logger.info if evento == "ws_cliente_desconectado" else logger.warning
    log_fn(evento, client=client_host, total_activos=len(active_websockets), **detalle)


class NormalizarMcpRutaMiddleware:
    """Normaliza /mcp a /mcp/ en memoria para responder directamente sin redirección 307."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") == "http" and scope.get("path") == "/mcp":
            scope = dict(scope)
            scope["path"] = "/mcp/"
            scope["raw_path"] = b"/mcp/"
        await self.app(scope, receive, send)


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

    # Con "*" no se permiten credenciales (la especificación CORS lo prohíbe).
    cors_abierto = (settings.CORS_ORIGINS or "").strip() == "*"
    if cors_abierto and not settings.DEBUG:
        raise ValueError("CORS_ORIGINS no puede ser '*' en producción")
    origins = (
        ["*"]
        if cors_abierto
        else list(
            dict.fromkeys(
                [o.strip() for o in (settings.CORS_ORIGINS or "").split(",") if o.strip()]
                + list(ORIGENES_CORS_CYBERSYN)
            )
        )
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=not cors_abierto,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[HEADER_DATOS_DESDE, HEADER_POTENCIA_REFERENCIA],
    )

    app.add_middleware(NormalizarMcpRutaMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(Exception, manejar_excepcion_no_mapeada)
    app.add_exception_handler(StarletteHTTPException, manejar_404)

    # Register Routers (asistente aislado según decisions/2026-09-24_bot-conversacional-aislamiento.md)
    routers = (system_router, disponibilidad_router, cargas_router, telemetria_router, dispositivos_router, organizaciones_router, planta_estructura_router, planes_router, alertas_router, auth_router, admin_router, audit_router, sge_router, usuarios_router, analitica_router, billing_router, produccion_router, notificador_router, maquinas_router, oauth_router, asistente_router)  # fmt: skip
    for r in routers:
        app.include_router(r)

    # WebSockets Live Telemetry Stream

    @app.websocket("/ws/live")
    async def websocket_stream(websocket: WebSocket):
        client_host = websocket.client.host if websocket.client else "desconocido"
        await websocket.accept()
        cliente = await _autenticar_cliente_ws(websocket, settings, client_host)
        if cliente is None:
            return
        _registrar_cliente_ws(cliente, client_host)
        try:
            await _bucle_recepcion_ws(websocket)
        except WebSocketDisconnect as e:
            _desconectar_cliente_ws(cliente, client_host, "ws_cliente_desconectado", code=e.code)
        except Exception as e:
            _desconectar_cliente_ws(cliente, client_host, "ws_cliente_error_conexion", error=str(e))

    # Servidor MCP Streamable HTTP para Claude Desktop / Claude Code / Claude.ai
    app.mount("/mcp", mcp_app)

    return app
