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

---

## 4. Convenciones de Nomenclatura en DTOs y Metrología

Para garantizar consistencia entre el backend (`datamaq-telemetry`) y el frontend (`app-datamaq`), los campos de datos siguen las siguientes reglas de sufijos:

* **Magnitudes Eléctricas:**
  * Potencia activa instantánea: `_W` (Vatios, ej. `potencia_activa_total_W`, `net_active_power_W`).
  * Potencia reactiva instantánea: `_VAR` (Volt-Amperios Reactivos, ej. `potencia_reactiva_total_VAR`).
  * Potencia aparente instantánea: `_VA` (Volt-Amperios, ej. `potencia_aparente_total_VA`).
  * Potencia de compensación calculada: `_kvar` (kVAr, ej. `potencia_reactiva_a_compensar_kvar`, `banco_sugerido_kvar`).
  * Tensiones: `_V` (Voltios RMS, ej. `voltage_V`, `voltage_linea_V`, `tension_neutro_estimada_V`).
  * Corrientes: `_A` (Amperios RMS, ej. `current_A`, `corriente_neutro_estimada_A`).
  * Energías acumuladas: `_kwh` / `_kvarh` (kWh / kVARh).
* **Porcentajes y Distorsión Armónica:**
  * Desbalances: `_porcentaje` (ej. `desbalance_tension_porcentaje`, `desbalance_corriente_porcentaje`).
  * Distorsión armónica: `_pct` (ej. `thd_v_pct`, `thd_i_pct`, `thd_v_promedio_pct`).
* **Valores Económicos:**
  * Moneda local argentina: `_ars` (ej. `penalizacion_estimada_ars`, `precio_mensual_ars`).
* **Identificadores Polimórficos:**
  * El parámetro `{device_id}` en rutas REST acepta indistintamente UUID v4 (`725dfb4c-...`) o dirección MAC del hardware (`D48C49F03564` o `d4:8c:49:f0:35:64`).
* **Semántica de Métodos HTTP:**
  * `PATCH`: Modificación parcial de metrología/configuración (`/api/dispositivos/{id}`) o resolución de estados (`/api/alertas/{id}/resolver`).
  * `PUT`: Sobreescritura idempotente de árboles (ej. `/api/v1/plantas/{id}/unifilar`, `/api/v1/plantas/{id}/layout`).

