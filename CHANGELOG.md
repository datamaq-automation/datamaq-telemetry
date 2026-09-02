# Changelog

Todos los cambios notables en este proyecto serán documentados en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/), y este proyecto adhiere a [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Sin publicar]

### Corregido
- **Aprovisionamiento de medidores Powermeter (documentación y tooling desalineados con el broker):**
  - [`docs/provisioning_guide.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/provisioning_guide.md) indicaba puerto `1883` con `NO-SECURITY` y usuario vacío. El broker escucha el `1883` solo en `127.0.0.1` y tiene `allow_anonymous false`, por lo que esa configuración impide toda conexión. Reescrita con la configuración obligatoria: `mqtt.datamaq.com.ar:8883`, `TLS-SERVER-AUTH`, CA ISRG Root X1 y usuario `datamaq_device`.
  - [`profiles/datamaq_server.json`](file:///home/agustin/proyectos_software/datamaq-telemetry/profiles/datamaq_server.json): usuario MQTT fijo y CA referenciada por archivo (`mqtt_ca_certificate_file`); la contraseña se inyecta con `--mqtt-password` o `MQTT_PASSWORD` y nunca se versiona.
  - [`scripts/provision_device.py`](file:///home/agustin/proyectos_software/datamaq-telemetry/scripts/provision_device.py): ya no publica el certificado CA cuando está vacío (ese POST **borraba** el CA del equipo y rompía el TLS); valida la configuración antes de escribir en el medidor (`_validar_config`); `--status` emite un veredicto explícito Wi-Fi vs. MQTT (`_diagnosticar`); propaga código de salida distinto de cero ante fallo.
  - [`scripts/logs.sh`](file:///home/agustin/proyectos_software/datamaq-telemetry/scripts/logs.sh): `--mqtt` leía `journalctl -u mosquitto` y siempre devolvía "No entries" porque el broker usa `log_dest file`; ahora lee `/var/log/mosquitto/mosquitto.log`. Nuevo filtro `--device [UID]` que descarta el escaneo de internet. `--status` inspeccionaba el puerto inexistente `8885` en vez de `8883`.
  - `isrg_root_x1.pem` (CA raíz pública de Let's Encrypt, necesaria para aprovisionar) dejó de estar en `.gitignore`.

### Corregido
- **Saneamiento del contrato de telemetría (cambios rompientes, ver [`docs/informe-cambios-contrato-telemetria.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/informe-cambios-contrato-telemetria.md)):**
  - **Timestamps sin zona horaria:** la API emitía `2026-09-01T23:20:00` sin offset y JavaScript lo interpretaba como hora local, mostrando las mediciones con tres horas de corrimiento. Nuevo `UtcDateTime(TypeDecorator)` como punto único de conversión en el borde de persistencia (cubre las 26 columnas sin cambio de DDL) y tipo anotado `FechaHoraUTC` en los 17 campos datetime de los DTOs. Unificado el formato entre REST y WebSocket.
  - **Veredictos sobre mediciones inexistentes:** `estado_fp` devolvía `OPTIMO` con el factor de potencia en `null`, y `estado_tension` devolvía `NORMAL` sin ninguna tensión medida. Nuevo estado `SIN_DATOS` en ambos enums y eliminación de los defaults optimistas del value object y del DTO, que además pasa a tipar con los enums de dominio en vez de `str` sin validar.
  - **Potencia aparente ausente o inconsistente:** el firmware compacto no publica `s`, la ingesta no la derivaba y la agregación la aproximaba con `hypot(P,Q)`, de modo que una consulta `raw` devolvía `null` donde la agregada devolvía un número con otra definición. Nuevo `CalculadoraPotenciaService` con $S = V \cdot I$ unificado en ingesta y agregación, con acotado obligatorio del factor de potencia a $[-1, 1]$.
  - **Indicadores saturados por cargas despreciables:** `calcular_desbalance_corriente` exige 5 A de corriente promedio (daba 170% con 0.9 A en una fase) y `calcular_analitica_completa` exige 500 W antes de dimensionar compensación (llegaba a estimar ARS 4.774 de penalización sobre 148 W de standby).
  - **Migración de backfill** que recalcula `apparent_power_*` y `power_factor_*` en el histórico, con SQL portable entre MySQL y SQLite.
  - **Simulador desalineado:** `scripts/mock_telemetry.py` emitía `s` y `pf` que el firmware real no publica, y el modo `seed` insertaba potencias aparentes con la semántica vieja; por eso ningún entorno de desarrollo reproducía el problema.

### Agregado
- **Auditoría de credenciales Wi-Fi:** `scripts/provision_device.py --wifi-audit` detecta caracteres no ASCII (homóglifos Unicode) en el SSID y la contraseña guardados en el medidor. Un homóglifo produce un PSK distinto y el equipo no se asocia jamás, sin mensaje de error; fue la causa raíz del incidente del 2026-09-01.
- **Documentación de diagnóstico de campo:** [`docs/troubleshooting-conectividad-dispositivos.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/troubleshooting-conectividad-dispositivos.md) — árbol de decisión Wi-Fi vs. broker, playbook de comandos y bitácora del incidente del 2026-09-01 (medidor `D48C49F03564`), incluidos el mapa de endpoints HTTP del firmware y dos trampas que invalidan lecturas: `status.json.wifi_sta.ssid` refleja la red asociada y no la configurada, y `mqtt_config.json` devuelve las credenciales siempre vacías por ser de solo escritura.

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
