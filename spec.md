# Spec B: Planes de Telemetría Freemium (Catálogo SaaS)

## 1. Objetivo y Contexto

Dotar a `datamaq-telemetry` de un catálogo de planes de suscripción para el
SaaS de telemetría de energía. Este catálogo es la **fuente de verdad** de la
escalera de conversión de la Fase 1 (AMBA Ya) publicada en `datamaq.com.ar`.

**Escalera real del negocio (contexto del CEO):**

0. Cursos gratuitos (LMS de `www-datamaq`).
1. Visita a planta + inspección de tablero para instalar Powermeter.
2. Relevamiento energético + facturas de electricidad.
3. SaaS de telemetría freemium (este módulo).

**Decisiones aprobadas por el CEO:**

- Cobro **manual vía WhatsApp** (sin pasarela de pago en Fase 1).
- Plan 0 **público y gratuito**: visibilidad pública, retención de 7 días,
  granularidad de potencia de 5 minutos, 1 dispositivo.
- Plan 1 **privado**: igual a Plan 0 pero de uso privado (plan pago).
- Plan 2 **privado**: mayor retención/almacenamiento y más dispositivos.
- Notificaciones por canal (email, telegram, whatsapp) según plan.

> [!NOTE]
> **Evolución del Modelo Freemium / PRO (Directiva Comercial):**  
> Ver documento canónico [`docs/to_www-datamaq.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/to_www-datamaq.md) para el modelo comercial activo:  
> • $0 de por vida (sin canon SaaS recurrente).  
> • 60 días de Versión PRO incluidos con cada instalación de medidor o consultoría energética (retención 365 días).  
> • Al expirar: Opción A (Vitrina Pública Anónima, 30 días de retención) vs. Opción B (Privado Básico, 14 días de retención y granularidad horaria). Implementado en el dominio en `PoliticaSuscripcionService`.

**Alcance de esta iteración:** entidad, puerto de repositorio, servicio de

política de retención, caso de uso de gestión, DTOs, controller y router
`GET /api/planes` + `POST /api/planes`. La persistencia SQLAlchemy (tabla
`plans`) y su repositorio se implementan en la fase GREEN junto con estos
contratos.

## 2. Dominio y Puertos

Sin dependencias externas en `domain/`. Se agregan a los módulos existentes:

### `src/domain/telemetria/value_objects.py`

- `VisibilidadPlan(str, Enum)` — `PUBLICO = "PUBLICO"`, `PRIVADO = "PRIVADO"`.

### `src/domain/telemetria/entities.py`

- `PlanTelemetria` (dataclass):
  - `id: str`
  - `nombre: str`
  - `descripcion: str`
  - `precio_mensual_ars: Decimal`
  - `visibilidad: VisibilidadPlan`
  - `retencion_dias: int`
  - `granularidad_minutos: int`
  - `max_dispositivos: int`
  - `canales_notificacion: list[str]`
  - `creado_en: datetime = field(default_factory=ahora_utc)`
  - `actualizado_en: datetime = field(default_factory=ahora_utc)`

### `src/domain/telemetria/ports.py`

- `RepositorioPlanesPort(ABC)`:
  - `listar_planes() -> list[PlanTelemetria]`
  - `obtener_por_id(plan_id: str) -> PlanTelemetria | None`
  - `guardar_plan(plan: PlanTelemetria) -> PlanTelemetria`

### `src/domain/telemetria/services.py`

- `PoliticaRetencionService` (servicio de dominio puro):
  - `ventana_consulta(plan: PlanTelemetria, ahora: datetime) -> datetime`
    — retorna `ahora - timedelta(days=plan.retencion_dias)`.

## 3. Casos de Uso y DTOs

### `src/application/dtos/plan_dto.py`

- `PlanCreateDTO(BaseModel)` — `nombre`, `descripcion`, `precio_mensual_ars`,
  `visibilidad`, `retencion_dias`, `granularidad_minutos`, `max_dispositivos`,
  `canales_notificacion`.
- `PlanResponseDTO(PlanCreateDTO)` — agrega `id`, `creado_en`, `actualizado_en`.

### `src/application/mappers/plan_mapper.py`

- `PlanMapper` — `create_dto_to_entity(dto, id) -> PlanTelemetria` y
  `to_dto(plan) -> PlanResponseDTO`.

### `src/application/use_cases/gestionar_planes.py`

- `GestionarPlanesUseCase(repo: RepositorioPlanesPort)`:
  - `listar_catalogo(solo_publicos: bool = False) -> list[PlanResponseDTO]`
    — si `solo_publicos`, filtra por `VisibilidadPlan.PUBLICO`.
  - `crear_plan(dto: PlanCreateDTO) -> PlanResponseDTO`.

### Controller y Router

- `src/infrastructure/fastapi/routes/planes_router.py` — `APIRouter(prefix="/api")`:
  - `GET /planes?solo_publicos={bool}` → `list_planes`.
  - `POST /planes` → `create_plan`.
- `src/infrastructure/fastapi/dependencies.py` — `get_planes_use_case`.
- `src/infrastructure/fastapi/server.py` — registrar `planes_router`.

## 4. Matriz de Pruebas (RED Suite)

### `tests/unit/test_planes.py`

1. `test_visibilidad_plan_enum` — `VisibilidadPlan.PUBLICO.value == "PUBLICO"`.
2. `test_plan_telemetria_valido` — construye la entidad y valida sus campos.
3. `test_politica_retencion_ventana` — `ventana_consulta` resta `retencion_dias`.
4. `test_listar_catalogo_solo_publicos` — filtra planes privados.
5. `test_crear_plan` — persiste y devuelve DTO con `id` generado.

### `tests/integration/test_planes_api.py`

1. `test_create_app_registra_router_planes` — `create_app()` expone `/api/planes`
   con métodos `GET` y `POST` (sin conexión a DB ni cliente HTTP).

## 5. Criterios del Gauntlet

```bash
pytest
pyright src/
ruff check .
ruff format --check .
```

Cobertura ≥ 85 %. Integridad: `__init__.py` de 0 bytes (sin re-exportaciones).

---

# Spec C: Optimización de Base de Datos y Caché de Ingesta (Lean / KISS)

## 1. Objetivo y Contexto

Optimizar el uso y rendimiento de la base de datos MySQL en la ingesta MQTT y en las definiciones de modelos, eliminando sobreescrituras innecesarias en disco y árboles de índices duplicados.

**Decisiones de diseño:**
- **Cero sobreingeniería:** No se aplica particionado de tablas ni tablas rollup para la Fase 1.
- **Limpieza de índices redundantes:** Remover `index=True` en `device_id` y `recorded_at` de `models.py` (ya cubiertos por los índices compuestos).
- **Caché de resolución de dispositivos:** `IngestarTelemetriaUseCase` mantiene un `_device_cache` en memoria (`MAC -> device_id`) para evitar `SELECT`s redundantes en cada mensaje.
- **Throttling de latidos (`last_seen_at`):** `IngestarTelemetriaUseCase` mantiene un `_ultimos_heartbeats` en memoria para amortiguar actualizaciones de estado en la tabla `devices` a 1 vez cada 60 segundos.

## 2. Casos de Uso y Modelos

### `src/application/use_cases/ingestar_telemetria.py`
- `_device_cache: ClassVar[dict[str, str]]`
- `_ultimos_heartbeats: ClassVar[dict[str, datetime]]`
- `_obtener_o_crear_dispositivo`:
  - Si la MAC está en `_device_cache` y el latido fue hace menos de 60s, devuelve el dispositivo/ID sin ejecutar `obtener_por_uid` ni `guardar`.
  - Si no está o venció la ventana de 60s, actualiza en DB y refresca la caché.

### `src/infrastructure/sqlalchemy/models.py`
- En `TelemetryInstantaneousModel`, `TelemetryEnergyModel`, `DeviceStatusLogModel`:
  - `device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)` (sin `index=True`).
  - `recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)` (sin `index=True`).

## 3. Matriz de Pruebas (RED Suite)

### `tests/unit/test_optimizacion_db.py`
1. `test_indices_modelos_sin_duplicados_redundantes` — valida que las columnas `device_id` y `recorded_at` no tengan índices simples redundantes aparte del compuesto.
2. `test_device_cache_resolucion_en_memoria` — valida que mensajes consecutivos de un medidor conocido no llamen a `obtener_por_uid` del repositorio.
3. `test_heartbeat_throttling_60s` — valida que múltiples mensajes en menos de 60s no emitan llamadas a `guardar(dispositivo)`.

## 4. Criterios del Gauntlet

```bash
pytest
ruff check .
python scripts/verify_architecture.py
```

---

# Spec D: API de Consulta y Resolución de Alertas de Telemetría

## 1. Objetivo y Contexto

Exponer endpoints REST para que el frontend del dashboard y operadores de planta puedan:
1. Consultar el listado de alarmas de medidores (`GET /api/alertas`), con filtros opcionales por `device_id` y `solo_abiertas` (alertas no resueltas).
2. Marcar una alarma como resuelta (`POST /api/alertas/{alerta_id}/resolver`), registrando la fecha de resolución `resolved_at`.

## 2. Dominio y Puertos

### `src/domain/telemetria/exceptions.py`
- `AlertaNoEncontradaError(Exception)` — lanzada cuando el ID de alerta no existe.

### `src/domain/telemetria/ports.py`
- `RepositorioTelemetriaPort`:
  - `listar_alertas(dispositivo_id: str | None = None, solo_abiertas: bool = False, limite: int = 100) -> list[AlertaDispositivo]`
  - `obtener_alerta_por_id(alerta_id: int) -> AlertaDispositivo | None`

## 3. Casos de Uso, DTOs y Mappers

### `src/application/dtos/alerta_dto.py`
- `AlertaResponseDTO(BaseModel)`: `id: int`, `dispositivo_id: str`, `tipo_alerta: str`, `severidad: str`, `mensaje: str`, `esta_resuelta: bool`, `disparada_en: datetime`, `resuelta_en: datetime | None`.

### `src/application/mappers/alerta_mapper.py`
- `AlertaMapper.to_dto(entity: AlertaDispositivo) -> AlertaResponseDTO`.

### `src/application/use_cases/gestionar_alertas.py`
- `GestionarAlertasUseCase(repo_telemetria: RepositorioTelemetriaPort)`:
  - `listar_alertas(dispositivo_id: str | None = None, solo_abiertas: bool = False, limite: int = 100) -> list[AlertaResponseDTO]`
  - `resolver_alerta(alerta_id: int) -> AlertaResponseDTO`

## 4. Adaptadores y Routers

- `src/infrastructure/fastapi/routes/alertas_router.py`:
  - `GET /api/alertas?device_id={str}&solo_abiertas={bool}&limite={int}`
  - `POST /api/alertas/{alerta_id}/resolver`
- `src/infrastructure/fastapi/dependencies.py` — `get_alertas_use_case`.
- `src/infrastructure/fastapi/server.py` — registrar `alertas_router`.

## 5. Matriz de Pruebas (RED Suite)

### `tests/unit/test_alertas.py`
1. `test_listar_alertas_con_filtro_abiertas_y_device`
2. `test_resolver_alerta_exitosa`
3. `test_resolver_alerta_inexistente_lanza_error`

### `tests/integration/test_alertas_api.py`
1. `test_create_app_registra_router_alertas`

## 6. Criterios del Gauntlet

```bash
pytest
ruff check .
python scripts/verify_architecture.py
```
