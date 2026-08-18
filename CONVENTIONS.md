# CONVENTIONS.md - Guía de Estilo y Convenciones de Desarrollo (Datamaq Telemetry)

## 1. Stack Tecnológico & Arquitectura
* **Lenguaje:** Python 3.10+ con tipado estricto (`typing`, `Annotated`, `dataclasses`).
* **Arquitectura:** Clean Architecture (Robert C. Martin / Ports & Adapters) + Domain-Driven Design (DDD).
* **Framework Web:** FastAPI (asíncrono, OpenAPI autodocumentado).
* **Broker & Ingesta:** Mosquitto MQTT + `paho-mqtt`.
* **Base de Datos:** MySQL  (relacional con índices de series temporales) + SQLAlchemy 2.0.
* **Validación & Serialización:** Pydantic v2 (`BaseModel`, `Field`, `ConfigDict`).
* **Configuración:** `pydantic-settings` (`BaseSettings`, `SettingsConfigDict`).
* **Testing:** `pytest`.
* **Linter & Formatter:** `ruff` y `pyright`.

---

## 2. Estructura de Directorios (Clean Architecture & DDD Temático)
```
src/
├── domain/                                      # 1. Capa de Dominio Pura (Solo stdlib + dataclasses)
│   └── telemetria/                              # Bounded Context temático
│       ├── __init__.py                          # (0 bytes)
│       ├── entities.py                          # Dispositivo, Planta, Organizacion, PlanTelemetria, Lecturas
│       ├── value_objects.py                     # MacAddress, Tension, Potencia, FactorPotencia, VisibilidadPlan
│       ├── services.py                          # AnalizadorCalidadEnergiaService, PoliticaRetencionService
│       ├── ports.py                             # RepositorioTelemetriaPort, RepositorioDispositivosPort, etc.
│       └── exceptions.py                        # Excepciones de negocio de dominio
│
├── application/                                 # 2. Capa de Aplicación (Casos de Uso, DTOs y Mappers)
│   ├── use_cases/                               # ingestar, consultar, gestionar_dispositivos, gestionar_planes, purgar, gestionar_alertas
│   ├── dtos/                                    # telemetria_dto, dispositivo_dto, organizacion_dto, plan_dto, purga_dto, alerta_dto
│   └── mappers/                                 # telemetria_mapper, dispositivo_mapper, plan_mapper, alerta_mapper
│
├── adapters/                                    # 3. Capa de Adaptadores (Agnósticos del Framework Web)
│   ├── gateways/                                # in_memory_event_broadcaster (PublicadorEventosPort)
│   └── presenters/                              # error_presenter (Mapeo a códigos de error estándar)
│
├── infrastructure/                              # 4. Capa de Infraestructura (Librerías externas y Frameworks)
│   ├── fastapi/                                 # Servidor FastAPI, dependencias y routers (/api/..., /ws/live)
│   ├── sqlalchemy/                              # Modelos DeclarativeBase MySQL, engine y repositorios
│   ├── paho_mqtt/                               # Listener daemon MQTT con Paho
│   └── settings/                                # Configuración con pydantic-settings y logger estructurado
│
└── main.py                                      # Entrypoint ASGI (app = create_app())
```

---

## 3. Convenciones Críticas
1. **Regla de Dependencia en Clean Architecture:**
   * Las capas internas (`domain`) nunca deben importar de capas externas (`application`, `adapters`, `infrastructure`).
   * `application` solo depende de `domain` y `pydantic`.
   * `adapters` depende de `application` y `domain` (nunca de `infrastructure` ni frameworks web).
   * `infrastructure` aísla frameworks y bases de datos (`fastapi`, `sqlalchemy`, `paho-mqtt`).
2. **Imports Absolutos:** Siempre `from src....`, nunca imports relativos.
3. **`__init__.py` de 0 bytes:** Todos los `__init__.py` en `src/` y `tests/` deben tener exactamente 0 bytes.
4. **Commits:** Conventional Commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`).
