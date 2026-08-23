# Changelog

Todos los cambios notables en este proyecto serán documentados en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/), y este proyecto adhiere a [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.3.0] - 2026-08-23

### Agregado
- **Analítica de Calidad de Energía y Compensación de Reactiva:**
  - Servicio de dominio [`DimensionadorCompensacionService`](file:///home/agustin/proyectos_software/datamaq-telemetry/src/domain/telemetria/analizador_reactiva.py) para cálculo de potencia reactiva a compensar ($Q_c$), recomendación de banco comercial normalizado y distribución de escalones modulares.
  - Estimación monetaria de penalización mensual en ARS por bajo factor de potencia ($\text{FP} < 0.95$) bajo régimen tarifario ENRE/Distribuidoras.
  - Cálculo de Desbalance de Corriente ($\text{IUR \%}$) bajo norma IEC 61000-4-30.
  - Value Object inmutable [`AnaliticaCalidadEnergia`](file:///home/agustin/proyectos_software/datamaq-telemetry/src/domain/telemetria/value_objects.py) y DTO [`AnaliticaCalidadEnergiaDTO`](file:///home/agustin/proyectos_software/datamaq-telemetry/src/application/dtos/telemetria_dto.py).
  - Inyección automática del bloque `analitica` en los endpoints `GET /api/telemetria/latest/{device_id}` y `GET /api/telemetria/instantaneous/{device_id}`.
- **Soporte de Verbos HTTP PATCH:**
  - Habilitado `PATCH /api/dispositivos/{id}` para actualización de configuración de metrología 2-TI (`fases_con_ti`, `tipo_instalacion`).
  - Habilitado `PATCH /api/alertas/{id}/resolver` para resolución de incidentes con observaciones.
- **Topología Unifilar y Layout 2D de Planta:**
  - Endpoints `GET /api/v1/planta/unifilar` y `PUT /api/v1/plantas/{id}/unifilar` con persistencia en `unifilar_nodes`.
  - Endpoints `GET /api/v1/planta/layout` y `PUT /api/v1/plantas/{id}/layout` con persistencia en `facility_zones` y `facility_device_layouts`.

### Cambiado
- **Arquitectura Documental:**
  - Unificada toda la documentación de integración frontend en [`docs/frontend-integration-guide.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/frontend-integration-guide.md).
  - Consolidado el índice maestro en [`docs/README.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/README.md).
  - Depurados memos transitorios de sprints anteriores.

---

## [1.2.0] - 2026-08-20

### Agregado
- **Autenticación Segura y Control de Acceso:**
  - Emisión de cookies `HttpOnly` (`datamaq_token`) con JWT firmado mediante algoritmo HMAC-SHA256 (`HS256`).
  - Endpoint de autenticación pública para invitados `POST /api/auth/guest` (stateless, sin I/O contra base de datos, con rate limiting por IP).
  - Endpoint de consulta de identidad `GET /api/auth/me`.
  - Matriz de control de acceso basada en roles (`admin`, `operador`, `invitado`).
  - Autenticación en WebSocket `/ws/live` mediante cookie en el handshake o cabecera `Authorization: Bearer`.
- **Hardening de Seguridad:**
  - Middleware de cabeceras de seguridad (`HSTS`, `CSP`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`).
  - Rate limiting de intentos fallidos de login con cabecera `Retry-After`.

---

## [1.1.0] - 2026-08-15

### Agregado
- **Calidad de Suministro Eléctrico y Diagnóstico:**
  - Cálculo de Desbalance de Tensión Trifásico ($\text{VUR \%}$) según norma IEC / NEMA.
  - Estimación matemática de Tensión de Neutro (`tension_neutro_estimada_V`) y Corriente de Neutro (`corriente_neutro_estimada_A`).
  - Filtro de persistencia temporal anti-transitorios (3 segundos) para supresión de falsas alarmas durante arranques de motores.
  - Detección automática en dominio de inversión de polaridad en transformadores de corriente (`TI_INVERTIDO`).
  - Soporte de configuración para acometidas trifásicas sin neutro y esquemas 2-TI (`phases_with_ct`).
- **Persistencia Temporal y Purga:**
  - Endpoint `POST /api/system/purge` y script CLI `scripts/purge_telemetry.py` para purga en lotes de datos expirados.
  - Modelo de políticas de retención diferenciadas por plan (`PoliticaSuscripcionService`).

---

## [1.0.0] - 2026-08-01

### Agregado
- **Lanzamiento Inicial de Datamaq Telemetry Platform:**
  - Motor de ingesta MQTT con worker en segundo plano `Paho-MQTT` suscrito a tópicos `m/wifi/#`.
  - Re-emisión instantánea de telemetría hacia WebSocket en vivo `/ws/live`.
  - Persistencia relacional en MySQL / MariaDB con SQLAlchemy 2.0 y migraciones automáticas Alembic.
  - Auto-registro de medidores Powermeter (SmartPlus, Home, Pro, Automate) vía mensajes de ciclo de vida `onoff`, `add`, `status`.
  - API REST FastAPI con OpenAPI autodocumentado (`/docs`, `/redoc`).
  - Arquitectura limpia (Clean Architecture + DDD temático) con verificador de reglas arquitectónicas `verify_architecture.py`.
  - Gauntlet de calidad pre-push y CI con cobertura de pruebas $\ge 85\%$.
