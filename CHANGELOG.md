# Changelog

Todos los cambios notables en este proyecto serán documentados en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/), y este proyecto adhiere a [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Sin publicar]

### Corregido
- **Alcance tarifario del cargo por reactiva (D-11): la exención nunca se ejecutaba en producción.** `categoria_tarifaria` y `penalizacion_reactiva_aplica` existían en el DTO de dispositivo desde antes, pero nunca fueron columnas reales de `devices` — `DispositivosRepository._to_entity`/`guardar` no las mapeaban en ningún sentido, así que `PATCH /api/v1/dispositivos/{id}` las aceptaba pero era un no-op silencioso: la categoría siempre volvía al default `"T2"`. Además, `_evaluar_abstencion_enre` eximía del cargo por "es monofásico" o "demanda < 10 kW", asumiendo monofásico/chico == residencial == exento — un T1-G (comercio, consorcio) monofásico con medición de reactiva sí está alcanzado por el régimen, y quedaba exento por error. Se corrigen ambos: migración + repositorio cableado de punta a punta, y la exención pasa a depender solo de `categoria_tarifaria`/`penalizacion_reactiva_aplica` explícitos.
- **`TelemetriaMapper.instantanea_to_dto` nunca recibía `dispositivo`.** Los tres callers reales (`GET /latest`, `GET /instantaneous`, publicador del WS `inst`) calculaban `analitica` sin pasar el dispositivo, así que `_evaluar_abstencion_enre(None)` devolvía `None` de inmediato — la exención tarifaria (aun antes de la corrección anterior) era código muerto en cualquier request real.
- **`telemetry_energy` con filas duplicadas cuando un medidor publica `acc` y `energyio`.** Ambos subtópicos escriben el mismo `(device_id, recorded_at)`; sin restricción, quedaban como dos filas (el medidor de la organización invitado tenía 50% de sus filas duplicadas). `guardar_energia` pasa a hacer upsert: `energyio` (registro total del equipo, prioritario) sobreescribe; `acc` (suma de fases, respaldo) solo inserta si no había fila. Migración con índice único `uq_energy_dev_time`; script `scripts/dedup_telemetry_energy.py` archiva (no borra) los duplicados históricos.

### Agregado
- **Jerarquía TGBT y permisos de planta por usuario** (respuesta al informe de delegación del frontend del 2026-09-13, [`docs/informe-respuesta-tgbt-permisos-planta.md`](docs/informe-respuesta-tgbt-permisos-planta.md)):
  - **R-01 no era una migración.** La jerarquía del unifilar vive en `data/organizaciones.yml`, no en MySQL, y `TipoNodoUnifilar` ya incluía `tgbt` con `parent_id`. Se reestructura la topología de Durax y UPP como `acometida MT (virtual) → transformador (virtual) → tgbt (medidor)`: el medidor se declara en el TGBT, que es lo que físicamente mide, y el trafo pasa a sumar a su TGBT. `NodoUnifilarDTO.tipo` pasa de `str` libre a vocabulario cerrado `acometida | transformador | tgbt | seccional | carga` (422 si se manda otro).
  - **R-02 `user_facility_access`** (migración `n8o9p0q1r2s3`): asignación explícita usuario ↔ planta con `can_switch`. `GET /api/v1/auth/me` devuelve `plantas[]` (`id`, `nombre`, `organizacion_id`, `puede_cambiar`) y `planta_activa_id`. Política (`PoliticaAccesoPlantasService`): `superadmin`/`invitado_global` ven todas las plantas y siempre pueden cambiar; usuario con filas ve solo esas (acotadas a su org); usuario sin filas conserva el comportamiento histórico (toda su org, con cambio). Administración por `GET`/`PUT /api/v1/usuarios/{id}/plantas` (admin de la misma org o superadmin).
  - **Potencias nominales inventadas, borradas.** `potencia_nominal_kw` de los trafos de Durax (300/150) y UPP (800/800) y de la acometida de Casa (5.5) no tenían fuente: los había completado un LLM. Se eliminan del YAML; regla nueva en `CONVENTIONS.md` §3.5 (sin fuente verificable, sin campo).
  - **R-03 `nombre_maquina`** en cada nodo del unifilar: nombre de la máquina 1:1 del medidor (`machines.device_id UNIQUE`) o `null`, resuelto con una sola consulta por planta.
- **Agregación de energía por periodo resuelta en SQL, no en Python.** `listar_acumulados_para_agregacion` cargaba la serie cruda completa (hasta ~87 000 filas por dispositivo, hasta 41 s medido en producción) para que el dominio se quedara con el último valor por periodo. `listar_ultimos_acumulados_por_periodo` hace esa reducción con `ROW_NUMBER()` particionado por periodo local en SQL, usando el índice `(device_id, recorded_at)` ya existente.
- **Throttle de persistencia para energía (300 s), con ventana independiente por fuente.** El medidor publica un acumulado cada ~2 s; solo importa el último valor de la ventana. Clave de throttle por `(dispositivo, fuente)`, no solo por dispositivo — compartir la ventana entre `acc` y `energyio` dejaría afuera al prioritario según quién llegue primero.
- **[`docs/adr-001-no-redis-cache.md`](docs/adr-001-no-redis-cache.md):** decisión de no incorporar Redis como cache sobre MySQL, fundamentada con métricas reales de producción (buffer pool hit 99,999 %, 7 q/s). Define los disparadores concretos que sí la justificarían.
- **[`docs/devops-mejoras-2026-09-13.md`](docs/devops-mejoras-2026-09-13.md):** el pipeline `CD Deploy` estuvo roto ~14 horas por `scripts/.env.deploy` commiteado con `DEPLOY_SSH_USER=root` (desrastreado). `scripts/guard_secrets.sh` bloquea, en CI y en el pre-push local, que un `.env` real vuelva a quedar trackeado. Límites de cgroup (`MemoryMax=512M`, `CPUQuota=150%`) para que el servicio no pueda acaparar el VPS compartido. Actions actualizadas a Node 24 nativo.

- **Arquitectura de Datos SGE e ISA-95 (Jerarquía Declarativa de Activos y Topología)**:
  - Formalización del modelo de datos de planta bajo estándares **ANSI/ISA-95** (Empresa -> Sitio -> Área/USE -> Unidad/Medidor) e **ISO 50001** (Sistemas de Gestión de la Energía). Documentado en [`docs/arquitectura-sge-isa95.md`](docs/arquitectura-sge-isa95.md) y `Spec E` en [`spec.md`](spec.md).
  - Desacoplamiento de la gestión física y organizacional de MySQL hacia un modelo declarativo GitOps versionado en `./data/` con soporte para estructura multinivel (`./data/organizaciones/{org}/plantas/{planta}/`).
  - Extensión de `NodoUnifilar` y `NodoUnifilarDTO` con metadatos energéticos de ISO 50001: `potencia_nominal_kw`, `uso_significativo`, `categoria_uso` y `variable_relevante`.
  - Verificador de consistencia referencial en startup (`lifespan` FastAPI) para auditar claves foráneas huérfanas entre MySQL y YAML.
- **Desagregación de cargas (NILM) sobre un medidor agregado** — implementa el paso 4 del roadmap de [`docs/disponibilidad-maquina-diseno-conceptual.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/disponibilidad-maquina-diseno-conceptual.md) §8, que había dejado el modelo de datos fuera de alcance. Documentado en [`docs/desagregacion-cargas-nilm.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/desagregacion-cargas-nilm.md); contrato para el frontend en [`docs/informe-cambios-contrato-cargas.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/informe-cambios-contrato-cargas.md). **Recurso nuevo y aditivo: no toca ningún DTO existente.**

  - **Contexto `src/domain/cargas/`** (stdlib puro): catálogo genérico de `Carga` con su `FirmaCarga`, `CampanaCaracterizacion` e `IntervaloActividadCarga`. Genérico a propósito — el domicilio es banco de pruebas de un motor que se aplica igual a un tablero industrial.
  - **`PerfiladorLineaBaseService`:** separa consumo permanente de consumo de actividad por percentil bajo en ventanas horarias. Es el único análisis que da un resultado sólido a 300 s **sin ninguna firma calibrada**. `delta_diurno_W` se reporta sin bautizarlo "iluminación": es todo lo que se suma de día y no se puede separar en escalones.
  - **`AnalizadorCiclosService`:** duración de encendido e inactividad (mediana y MAD), duty cycle, período, e inferencia de `PatronOperacion`, con `INDETERMINADO` cuando no alcanza la evidencia. Histéresis opcional para que una carga que roza el umbral no se fragmente hasta desaparecer.
  - **`DetectorEscalonesService`:** escalones (ΔP, ΔQ) con umbral calibrado del ruido de la propia serie —una constante fija sería ciega en un tablero de 200 kW— y emparejado de cada encendido con su apagado. Descarta huecos de datos, episodios de más de 6 h y episodios de potencia media negativa: no describen una carga real.
  - **`EmparejadorFirmasService`:** puntaje multiplicativo de cuatro factores. La **duración** es el único eje que separa entre sí a pava, anafe, termotanque y horno, indistinguibles por potencia y por factor de potencia. Se abstiene (`NO_ATRIBUIDO`) ante baja confianza o ambigüedad: un residual honesto es utilizable, una atribución equivocada envenena el dataset etiquetado.
  - **`CalibradorFirmaService` y campañas de caracterización:** miden la firma real poniendo el medidor en ráfaga durante una ventana acotada, **sin tocar la cadencia permanente de 300 s ni el downsampling de la ingesta**. Tipo `ACTIVA` para lo que se prende a voluntad y `PASIVA` para lo que cicla solo (heladera, freezer, termotanque). Una campaña con otra carga entrando en el medio se cierra como `CONTAMINADA` y no emite firma.
  - **`AtribuidorConsumoService`:** reparte kWh contra el total exacto del contador acumulado (no integrando la serie instantánea, que sería sesgada). El residual `NO_ATRIBUIDO` es salida de primera clase; si lo atribuido supera al consumo real, lo denuncia en vez de repartir la diferencia.
  - **Captura durante campaña:** `CapturadorCampanaIngesta` es un sumidero paralelo en la ingesta que persiste a caudal completo en `campaign_samples`. No altera la serie permanente. Aprovecha que `realtime_sync_mode` ya se renovaba para el WebSocket y ese caudal de 1-5 s se estaba descartando.
  - **Motor batch idempotente:** `scripts/analizar_consumo.py` + `systemd/datamaq-analisis.{service,timer}` (horario) y `POST /api/v1/cargas/analisis`. Re-correr una ventana reescribe sus intervalos en vez de duplicarlos, y **nunca pisa una fila con `origin = 'CORRECCION_HUMANA'`**: esas filas son el dataset etiquetado y es lo único que ninguna regla puede regenerar.
  - **Migraciones** `e2f3a4b5c6d7`, `f3a4b5c6d7e8` y `a4b5c6d7e8f9`: `loads`, `characterization_campaigns`, `campaign_samples` y `load_activity_intervals`, con claves de unicidad que dan idempotencia ante el redelivery de MQTT QoS 1 y ante el reproceso del batch.
  - **Límite declarado:** a 300 s de cadencia la pava (2-4 min) y la iluminación no son detectables como eventos. `advertencia_cadencia` viaja en el contrato para que el consumidor distinga "no hubo" de "no se pudo ver".

### Cambiado
- `LecturaPotenciaTemporal` suma `potencia_reactiva_var` y `factor_potencia` opcionales. La potencia reactiva ya se persistía sin que ningún análisis la usara, y es el eje que separa una carga resistiva de una con motor.
- `alembic/env.py` y `scripts/generate_erd.py` importan explícitamente `models_cargas` para que sus tablas entren en la metadata.

### Cambiado
- **Versionado de API — `BREAKING CHANGE`:** todos los endpoints de negocio pasan de `/api/{recurso}` a `/api/v1/{recurso}` (auth, dispositivos, telemetría, alertas, planes, organizaciones/plantas, y las rutas de sistema `ws-status`/`purge`). Se formaliza la política de versionado (por recurso, no global) en [`CONVENTIONS.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/CONVENTIONS.md#5-versionado-de-api-y-compatibilidad-con-el-frontend). `planta_estructura_router` (`/api/v1/planta/*`) ya cumplía la convención y no cambia. Quedan sin versionar, deliberadamente, las sondas de infraestructura (`/health*`, `/favicon.ico`) y el WebSocket `/ws/live`. Requiere desplegar `app-datamaq` en la misma ventana que este backend, dado que las rutas cambian sin convivencia temporal de la versión anterior.

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
