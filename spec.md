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

- `src/adapters/controllers/planes_controller.py` — `PlanesController`.
- `src/infrastructure/fastapi/routes/planes_router.py` — `APIRouter(prefix="/api")`:
  - `GET /planes?solo_publicos={bool}` → `list_planes`.
  - `POST /planes` → `create_plan`.
- `src/infrastructure/fastapi/dependencies.py` — `get_planes_controller`.
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
