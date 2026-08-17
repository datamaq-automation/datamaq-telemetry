# Spec G: Robustez del Listener MQTT (Hardening de Ingesta)

## 1. Objetivo y Contexto

Endurecer el listener MQTT (`src/infrastructure/paho_mqtt/mqtt_listener.py`)
contra los 9 hallazgos detectados en la auditoría de robustez. Objetivo:
**el pipeline de ingesta no debe bloquearse ni perder/duplicar datos** ante
alta tasa de mensajes, caídas del broker o reentregas QoS 1.

**Inventario de hallazgos (origen del alcance):**

| # | Severidad | Hallazgo |
|---|-----------|----------|
| H1 | CRÍTICO | `_on_message` ejecuta toda la cadena MySQL síncrona en el callback de Paho → satura el loop de red |
| H2 | CRÍTICO | `_on_disconnect` solo loguea; sin reconexión ni backoff |
| H3 | ALTO | QoS 1 sin deduplicación → lecturas/acumulados duplicados |
| H4 | ALTO | `clean_session=True` pierde mensajes QoS 1 pendientes en caídas |
| H5 | MEDIO | Payload JSON válido pero no `dict` (`[1,2,3]`, `"string"`) pasa el filtro |
| H6 | MEDIO | Sin `on_subscribe` / `on_log` → sin visibilidad de fallos de suscripción |
| H7 | MEDIO | `MQTT_TOPIC_PREFIX` sin validación de formato de filtro MQTT |
| H8 | BAJO | `connect_async` sin verificación de conexión ni estado expuesto |
| H9 | BAJO | TLS solo `ca_certs`; sin mTLS (certfile/keyfile) |

**Decisiones aprobadas (usuario):**

- **Sesión persistente:** MQTTv311 + `clean_session=False` (protocolo por
  defecto de paho 2.x; máxima compatibilidad Mosquitto/EMQX). El broker debe
  tener `persistence true` (ya configurado en `deploy/mosquitto/mosquitto.conf`).
- **Healthcheck:** `GET /health` expone `mqtt_conectado: bool`.
- **Dimensionamiento hardware:** VPS compartido verificado (2 vCPU / 3,8 GiB,
  load 0,89, ~6 apps conviviendo). Defaults conservadores:
  `MQTT_WORKER_MAX_THREADS=2`, `DB_POOL_SIZE=4`, `DB_MAX_OVERFLOW=8`.
- **Restricción operativa:** `--workers 1` en uvicorn es **obligatorio por
  diseño** (el listener es singleton con cachés en memoria; N workers
  duplicarían la suscripción MQTT → ingesta duplicada). Documentado, no un
  bug de hardware.

**Fuera de alcance:** cambios de esquema de BD, pasarela de pago, registro
público de usuarios, particionado de tablas.

---

## 2. Dominio y Puertos

Sin dependencias de terceros en `domain/` (solo stdlib).

### `src/domain/telemetria/services.py`

- `FiltroDeduplicacionService` (servicio de dominio puro, thread-safe vía
  `threading.Lock` interno):
  - `__init__(ventana_segundos: int = 120)` — ventana temporal de retención.
  - `es_duplicado(clave: str, ahora: datetime | None = None) -> bool`
    — `True` si `clave` ya fue vista dentro de la ventana; `False` en caso
    contrario (y la registra). Poda entradas vencidas en cada llamada.
  - `limpiar() -> None` — vacía el registro (para tests y reinicios).

### `src/domain/telemetria/ports.py`

Sin cambios.

---

## 3. Casos de Uso e Infraestructura

### `src/domain/telemetria/services.py`

- La deduplicación es política de dominio (at-least-once → exactly-once) y
  vive como servicio puro, testeable sin paho.

### `src/infrastructure/settings/config.py`

Nuevos campos (con `field_validator` para el tópico):

- `MQTT_CLEAN_SESSION: bool = False`
- `MQTT_RECONNECT_MIN_DELAY_SEG: int = 1`
- `MQTT_RECONNECT_MAX_DELAY_SEG: int = 60`
- `MQTT_DEDUP_VENTANA_SEGUNDOS: int = 120`
- `MQTT_WORKER_MAX_THREADS: int = 2`
- `MQTT_TLS_CERTFILE: str = ""`
- `MQTT_TLS_KEYFILE: str = ""`
- `MQTT_LOG_LEVEL: str = "WARNING"` (nivel paho → logger)

`field_validator` sobre `MQTT_TOPIC_PREFIX`:
- Debe ser un filtro MQTT sintácticamente válido: no vacío, sin espacios,
  `#` solo como último nivel y tras `/` (o como tópico completo), `+` solo
  como nivel completo.
- Debe contener al menos un comodín (`+` o `#`) para evitar suscripciones
  de un único tópico exacto que fallarían silenciosamente.
- Rechaza `m/wifi` (sin comodín), `m/#/x`, `m wifi/#`, `""`, `#x`,
  `m/wifi/#/extra`.

Nuevos campos de BD (parametrización del pool, antes hardcodeado):

- `DB_POOL_SIZE: int = 4`
- `DB_MAX_OVERFLOW: int = 8`

### `src/infrastructure/sqlalchemy/database.py`

- `create_engine(..., pool_size=settings.DB_POOL_SIZE,
  max_overflow=settings.DB_MAX_OVERFLOW)` — reemplaza los valores hardcodeados
  10/20 por los settings (defaults conservadores para VPS compartido).

### `src/infrastructure/paho_mqtt/mqtt_listener.py`

Cambios estructurales:

- `__init__`:
  - `mqtt.Client(CallbackAPIVersion.VERSION2, client_id=..., clean_session=settings.MQTT_CLEAN_SESSION)`.
  - `client.reconnect_delay_set(min_delay=settings.MQTT_RECONNECT_MIN_DELAY_SEG, max_delay=settings.MQTT_RECONNECT_MAX_DELAY_SEG)`.
  - `client.tls_set(ca_certs=..., certfile=settings.MQTT_TLS_CERTFILE (si no vacío), keyfile=settings.MQTT_TLS_KEYFILE (si no vacío))`.
  - Registrar `on_subscribe = self._on_subscribe` y `client.on_log = self._on_log`.
  - `self._executor = ThreadPoolExecutor(max_workers=settings.MQTT_WORKER_MAX_THREADS)`.
  - `self._dedup = FiltroDeduplicacionService(settings.MQTT_DEDUP_VENTANA_SEGUNDOS)`.
  - `self._esta_conectado = False` (flag thread-safe).
- `_on_connect`:
  - `reason_code == 0` → `self._esta_conectado = True` + log + `client.subscribe(qos=1)`.
  - `reason_code != 0` → `self._esta_conectado = False` + log error.
- `_on_disconnect`:
  - Actualizar `self._esta_conectado = False` + log.
  - Si `reason_code != 0` y `self.is_running` → `client.reconnect()` con try/except
    (backoff gestionado por paho vía `reconnect_delay_set`).
- `_on_subscribe`: loguea `granted_qos`; si algún grant es `128`
  (suscripción rechazada) → log error.
- `_on_log`: reenvía logs de nivel paho al logger de la app (mapeado
  `MQTT_LOG_*` → nivel structlog).
- `_on_message` (validación y encolado síncronos; trabajo DB en worker):
  1. Descartar payload > `MQTT_MAX_PAYLOAD_BYTES` (como hoy).
  2. Decodificar + `json.loads`; si error → log + return.
  3. **Validar `isinstance(payload, dict)`**; si no → `mqtt_payload_no_dict` + return.
  4. Log debug `mqtt_mensaje_recibido` (sin payload bruto, como hoy).
  5. **Deduplicar** con clave `(topic, sha256(payload_bytes))`; si duplicado
     → log debug + return (no se encola).
  6. Encolar `(topic, payload)` en el `_executor` (futuro) y **retornar de inmediato**.
- `_procesar_mensaje(topic, payload)` (método separado, ejecutado en el worker):
  - Crea la sesión DB **dentro del worker** (thread-bound), instancia repos y
    `IngestarTelemetriaUseCase`, ejecuta `use_case.ejecutar(topic, payload)`,
    `db.close()` en `finally`.
- `esta_conectado() -> bool` — getter thread-safe del flag.
- `start()`: como hoy (`connect_async` + `loop_start`); `is_running=True`
  **antes** de conectar.
- `stop()`: `is_running=False` → `loop_stop()` → `disconnect()` →
  `self._executor.shutdown(wait=True)`.

### `src/application/use_cases/ingestar_telemetria.py`

- Agregar `_lock: ClassVar[threading.Lock]` (módulo-level) que proteja las
  secciones de lectura/escritura de `_device_cache`, `_ultimos_heartbeats` y
  `_ultimas_persistencias` (ahora accedidas desde múltiples workers).

### `src/infrastructure/fastapi/routes/system_router.py`

- `GET /health` responde `{"status": "healthy", "timestamp": ...,
  "mqtt_conectado": <bool>}`. El estado se obtiene de una dependencia que
  expone el listener.

### `src/infrastructure/fastapi/dependencies.py`

- Nuevo helper singleton para exponer el `MQTTListener` (estado de conexión)
  a `system_router` sin acoplar `system_router` a la instanciación.

### `src/infrastructure/fastapi/server.py`

- El `MQTTListener` instanciado en `lifespan` se registra en el helper de
  dependencias para que `/health` pueda consultar `esta_conectado()`.

---

## 4. Matriz de Pruebas (RED Suite)

### `tests/unit/test_mqtt_robustez.py`

**Filtro de deduplicación (dominio):**

1. `test_deduplicacion_descarta_duplicado_dentro_ventana` — `es_duplicado`
   retorna `True` la 2ª vez para la misma clave.
2. `test_deduplicacion_permite_tras_vencer_ventana` — con `ahora` avanzado
   más allá de `ventana_segundos`, `es_duplicado` retorna `False`.
3. `test_deduplicacion_clave_distinta_no_duplica` — claves distintas retornan
   `False` (la clave incluye el tópico).
4. `test_deduplicacion_poda_entradas_vencidas` — tras vencer, la entrada se
   elimina del registro interno.

**Encolado en workers (H1):**

5. `test_on_message_encola_y_retorna` — `session_factory` NO se invoca dentro
   de `_on_message`; el mensaje se encola (future agregado).
6. `test_worker_procesa_mensaje_encolado` — `_procesar_mensaje` (worker)
   ejecuta el use case con el payload dict.
7. `test_stop_apaga_executor` — `stop()` invoca `loop_stop`, `disconnect` y
   `shutdown(wait=True)` del executor.

**Validación de payload (H5):**

8. `test_payload_json_lista_descartado` — `[1,2,3]` → `mqtt_payload_no_dict`.
9. `test_payload_json_string_descartado` — `"string"` → `mqtt_payload_no_dict`.
10. `test_payload_vacio_procesado` — payload vacío → `{}` (comportamiento
    actual preservado).

**Reconexión y sesión (H2, H4):**

11. `test_init_configura_reconnect_delay_set` — `reconnect_delay_set` invocado
    con los delays configurados.
12. `test_on_disconnect_rc_no_cero_reconecta` — `rc != 0` + `is_running` →
    `client.reconnect()` invocado.
13. `test_on_disconnect_rc_cero_no_reconecta` — `rc == 0` → no reconecta.
14. `test_client_clean_session_false` — constructor recibe `clean_session=False`.

**Observabilidad y estado (H6, H8):**

15. `test_on_subscribe_logea_grants` — `_on_subscribe` loguea `granted_qos`.
16. `test_on_subscribe_qos_128_logea_error` — grant `128` → log de error.
17. `test_esta_conectado_true_tras_on_connect` — `on_connect` rc 0 prende flag.
18. `test_esta_conectado_false_tras_on_disconnect` — `on_disconnect` apaga flag.

**Configuración (H7):**

19. `test_topic_prefix_invalido_rechazado` — `m/wifi` (sin `#`), `m/#/x`,
    `m wifi/#`, `""` → `ValidationError`.
20. `test_topic_prefix_valido_aceptado` — `m/wifi/#`, `m/+/#` → OK.
21. `test_defaults_robustez_mqtt` — defaults de los 8 settings nuevos
    (clean_session False, delays 1/60, ventana dedup 120, workers 2,
    pool 4/8).

**mTLS (H9):**

22. `test_tls_mutuo_cuando_certfile_configurado` — `tls_set` recibe
    `certfile`/`keyfile` cuando están configurados.

**Concurrencia use case (H1 derivado):**

23. `test_use_case_cache_lock` — las cachés `ClassVar` del use case están
    protegidas por `threading.Lock`.

### `tests/unit/test_security_mqtt.py` (compatibilidad)

Los tests existentes siguen verdes: validación de tamaño, log sin payload y
TLS permanecen síncronos en `_on_message`/`__init__`. El helper `_listener`
construye con `__new__` (no ejecuta `__init__`), por lo que no requiere
executor.

---

## 5. Criterios del Gauntlet

```bash
venv/bin/python scripts/verify_architecture.py
venv/bin/ruff check .
venv/bin/ruff format --check .
venv/bin/pytest --cov=src
venv/bin/pyright src/
```

Reglas inmutables: `__init__.py` de 0 bytes; prohibidos `# type: ignore`,
`# noqa`, `cast(Any, ...)`, `@pytest.mark.skip`; cero re-exportaciones.

Cobertura: los módulos nuevos y modificados
(`mqtt_listener.py`, `FiltroDeduplicacionService`,
`ingestar_telemetria.py`, `config.py`, `database.py`,
`system_router.py`, `server.py`, `dependencies.py`) deben quedar con
cobertura relevante (≥ 85 % en las ramas nuevas del listener y del filtro de
deduplicación).
