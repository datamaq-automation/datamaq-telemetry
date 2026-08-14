# CONVENTIONS.md - Guía de Estilo y Convenciones de Desarrollo (Datamaq Telemetry)

## 1. Stack Tecnológico & Arquitectura
* **Lenguaje:** Python 3.10+ con tipado estricto (`typing`, `Annotated`, `dataclasses`).
* **Arquitectura:** Clean Architecture (Robert C. Martin / Ports & Adapters) + Domain-Driven Design (DDD).
* **Framework Web:** FastAPI (asíncrono, OpenAPI autodocumentado).
* **Broker & Ingesta:** Mosquitto MQTT + `paho-mqtt`.
* **Base de Datos:** MySQL / MariaDB (relacional con índices de series temporales) + SQLAlchemy 2.0.
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
│       ├── entities.py                          # Dispositivo, MedicionFase, LecturaInstantanea
│       ├── value_objects.py                     # MacAddress, Tension, Potencia, FactorPotencia
│       ├── services.py                          # AnalizadorCalidadEnergiaService
│       ├── ports.py                             # RepositorioTelemetriaPort, RepositorioDispositivosPort
│       └── exceptions.py                        # Excepciones de negocio
│
├── application/                                 # 2. Capa de Aplicación (Casos de Uso y DTOs)
│   ├── use_cases/                               # IngestarTelemetriaUseCase, ConsultarTelemetriaUseCase
│   ├── dtos/                                    # Data Transfer Objects Pydantic v2
│   └── mappers/                                 # Mapeadores Entidad <-> DTO
│
├── adapters/                                    # 3. Capa de Adaptadores (Agnósticos del Framework Web)
│   ├── controllers/                             # TelemetriaController, DispositivosController
│   ├── gateways/                                # InMemoryEventBroadcaster
│   └── presenters/                              # ErrorPresenter (Mapeo a códigos HTTP y errores)
│
├── infrastructure/                              # 4. Capa de Infraestructura (Librerías externas)
│   ├── fastapi/                                 # Servidor FastAPI, routers HTTP, WebSockets
│   ├── sqlalchemy/                              # Tablas ORM MySQL, database engine y repositorios
│   ├── paho_mqtt/                               # Listener daemon MQTT
│   └── pydantic/                                # Settings con pydantic-settings
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
