# Réplica de datos y flujo en vivo para `develop` (api-dev)

> **Decisión:** `decisions/2026-10-29_invitado-develop-replica.md` (repo padre).
> **Alcance:** solo modo `develop` (`api-dev`, `app-dev`). **No** cambia `main`.
> **Estado:** spec, sin código. La implementación queda detrás de la aprobación de esta spec.

## 1. Objetivo y Contexto

La cuenta `invitado@datamaq.com.ar` tiene que ver datos históricos y en tiempo real desde `develop`, sin tocar
producción. El dueño aceptó datos reales en la réplica y el flujo en vivo del broker, con una condición: `develop`
**no persiste** lo que recibe del broker y **no escribe** en la réplica.

Esta spec responde dos preguntas con evidencia del código de `origin/develop`:

- **(a) ¿la ingesta escribe siempre, o hay un camino sin escritura?** Escribe siempre. No hay un camino sin escritura
  dentro de la ingesta. El flujo en vivo sale del mismo método que la persistencia, así que hace falta un corte nuevo.
- **(b) ¿qué puede hacer el rol `operador`?** Puede escribir en 24 endpoints. El rol no es de solo lectura.

## 2. Respuestas con evidencia (`origin/develop`)

### 2.1 La ingesta siempre escribe

Cada mensaje del broker pasa por `_ejecutar_ingesta` (`src/infrastructure/paho_mqtt/mqtt_listener.py:203-246`), que
arma `IngestarTelemetriaUseCase` con el repositorio de telemetría y el de dispositivos (`mqtt_listener.py:236-244`).
Las escrituras que hace ese camino:

| Escritura | Dónde | Línea |
|---|---|---|
| Lectura instantánea (`guardar_instantanea`) | `src/application/use_cases/ingestar_telemetria.py` | 194 |
| Energía acumulada (`guardar_energia`) | `ingestar_telemetria.py` | 248 |
| Log de estado (`guardar_log_estado`) | `ingestar_telemetria.py` | 268 |
| Alerta de evento del medidor (`guardar_alerta`) | `ingestar_telemetria.py` | 285 |
| Anomalía de coherencia (`guardar_anomalia`) | `ingestar_telemetria.py` | 316 |
| Alertas de calidad (`guardar_alerta`) | `src/application/use_cases/ingesta/procesador_alertas_ingesta.py` | 65, 80, 116 |
| Dispositivo: alta automática y heartbeat (`guardar`, `actualizar_heartbeat`) | `src/application/use_cases/ingesta/resolvedor_dispositivo.py` | 61, 115, 124 |
| Eventos de disponibilidad (`guardar`) | `src/application/use_cases/gestionar_disponibilidad.py` | 107, 122, 141, 160 |
| Campaña de caracterización (`capturar`) | `src/application/use_cases/ingesta/capturador_campana.py` | 56 |
| THD por instantánea (`actualizar_thd_instantanea`) | `src/application/use_cases/ingestar_harmonics_thd.py` | 57 |

No hay un flag que apague la escritura. Lo que existe es `MQTT_HABILITADO` (`src/infrastructure/settings/config.py:42`,
usado en `src/infrastructure/fastapi/server.py:334, 371-372`): apaga **todo** el listener, incluido el flujo en vivo.
Eso no sirve: `develop` necesita el flujo en vivo.

El flujo en vivo sale antes de las escrituras y por un canal aparte: `self.publicador.publicar_telemetria_en_vivo(...)`
en `ingestar_telemetria.py:130-131` (todos los subtópicos salvo `inst` y `harmonics`) y `:160-164` (instantánea). Ese
canal es el que tiene que quedar. Las escrituras, no.

**Conclusión (a):** no hay camino sin escritura. Hace falta un corte explícito.

### 2.2 Qué puede hacer el rol `operador`

Fuente: `docs/matriz-roles-permisos.md` de `develop` (generada desde las rutas) y el guard en código.

- Guard de escritura: `src/infrastructure/fastapi/dependencies.py:500-507` (`requiere_rol_escritura`). La lista
  permitida incluye `operador`.
- La matriz muestra **24 endpoints que no son GET y que `operador` puede ejecutar**, entre ellos:
  - `POST /api/v1/dispositivos`, `PATCH` y `PUT /api/v1/dispositivos/{device_id}`;
  - `POST /api/v1/planes`;
  - `POST /api/v1/cargas`, `PATCH /api/v1/cargas/{carga_id}`, `PUT /api/v1/cargas/{carga_id}/firma`, y las campañas;
  - `POST /api/v1/disponibilidad/maquinas`, `POST /api/v1/disponibilidad/paradas-programadas`;
  - `PATCH` y `POST /api/v1/alertas/{alerta_id}/resolver`;
  - `POST /api/v1/auth/2fa/activar`, `/desactivar`, `/setup` (guard `no_permitido_para_invitados_2fa`).
- La mayoría de los GET no lleva guard de rol: cualquier usuario autenticado puede leer, incluido `operador` (la matriz marca 87 filas con "todos (sin guard)", que incluyen rutas públicas; no separé cuáles son GET autenticados).

**Conclusión (b):** `operador` no es de solo lectura. "Solo lectura" no se puede lograr con el rol: hay que garantizarlo
en la base y en la API para esta cuenta.

## 3. Propuesta

### 3.1 Historial desde la réplica

- DevOps crea la réplica y el usuario de solo lectura en la VPS (fuera de esta spec; requiere autorización del dueño).
- Telemetry solo configura `api-dev`: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` (`config.py:15-21`).
  No hace falta código nuevo para leer de la réplica.
- Efecto: cualquier escritura de `api-dev` contra la réplica **falla en la base**, porque el usuario no tiene permisos
  de escritura. Ese es el criterio de prueba "una escritura en la réplica falla".

### 3.2 Flujo en vivo sin persistir

Flag nuevo `INGESTA_PERSISTENCIA_HABILITADA` (booleano, default `true`), definido en el entorno de `api-dev`, no en
una rama de código.

- Composition root: `mqtt_listener.py:236-244`. Cuando el flag es `false`, los repositorios de telemetría, dispositivos
  y eventos de disponibilidad se pasan envueltos en un adaptador que **no escribe**: los métodos `guardar*`,
  `actualizar*` y `capturar` devuelven sin hacer nada y dejan un log `ingesta_sin_persistencia`.
- Resultado: el publicador en vivo sigue recibiendo cada mensaje (`ingestar_telemetria.py:130-131, 160-164`), y ninguna
  escritura llega a la base. Un solo punto de corte, sin tocar las capas de dominio ni aplicación.

### 3.3 Comandos al broker (fuera de lo pedido, pero necesario)

El flujo en vivo es de solo lectura, pero el backend también **escribe hacia los medidores**. Eso contradice la
decisión ("solo lectura sobre el broker"):

- `publicar_comando` (`mqtt_listener.py:276`) y `activar_tiempo_real_dispositivo` (`mqtt_listener.py:289`) publican en
  `m/wifi/{UID}/conf/com`.
- La renovación automática de la ráfaga (`server.py:319-323` y `:443-448`, y `dispositivos_router.py:187`) llama a esos
  comandos mientras haya clientes WebSocket conectados.

Propuesta: flag `MQTT_COMANDOS_HABILITADOS` (default `true`). En `api-dev`, `false`: los comandos devuelven `False`
sin publicar y se loguean. El dueño decide si `develop` tiene que renovar la ráfaga (ver D2).

### 3.4 Cuenta `invitado@datamaq.com.ar` como `operador`

- Rol: `operador` (el rol `invitado` ya no existe en el backend).
- Como `operador` puede escribir, la solo lectura de la cuenta **no** se garantiza con el rol. Se propone:
  - (1) el usuario de la réplica sin permisos de escritura (3.1), y
  - (2) un guard de método en `api-dev`: flag `MODO_SOLO_LECTURA` que rechace con 403 todo método distinto de
    `GET`/`HEAD`/`OPTIONS` para las cuentas con rol `operador`, o para todas las sesiones de `api-dev`.
- La cuenta se crea después de aprobar esta spec y con autorización del dueño.

## 4. Matriz de pruebas

| Prueba | Capa | Verifica |
|---|---|---|
| `test_flag_apagado_no_escribe_telemetria` | infra | con `INGESTA_PERSISTENCIA_HABILITADA=false`, `guardar_instantanea` y `guardar_energia` no se llaman |
| `test_flag_apagado_sigue_publicando_en_vivo` | infra | el publicador recibe la instantánea aunque no se persista |
| `test_flag_apagado_no_crea_dispositivos` | infra | `resolvedor_dispositivo` no llama `guardar` |
| `test_comandos_apagados_no_publican` | infra | con `MQTT_COMANDOS_HABILITADOS=false`, `publicar_comando` devuelve `False` y no publica |
| `test_modo_solo_lectura_rechaza_escrituras` | infra | `POST /api/v1/dispositivos` con rol `operador` devuelve 403 |
| `test_modo_solo_lectura_permite_get` | infra | `GET` de telemetría con rol `operador` responde 200 |
| `test_escritura_en_replica_falla` | integración (VPS, no CI) | usuario de la réplica: `INSERT` rechazado por la base |
| `test_flujo_en_vivo_no_crea_filas` | integración (dev) | con el flag en `false`, contar filas antes y después de N mensajes: sin diferencia |

Las dos primeras pruebas de integración (réplica y flujo en vivo) corren en `develop` con una base descartable. No
usan la base real.

## 5. Criterios de aceptación

- En `develop`, una escritura contra la réplica falla.
- El flujo en vivo no crea filas nuevas en ninguna tabla.
- La cuenta `invitado@` no puede escribir, aunque su rol sea `operador`.
- Con los flags en su default, el comportamiento de `main` no cambia (prueba: `pre-push` verde sin flags).

## 6. Decisiones del dueño

- **D1 — Guard de método en `develop`.** ¿El guard de solo lectura (3.4) aplica a todas las sesiones de `api-dev` o
  solo a la cuenta `invitado@`?
- **D2 — Ráfaga en `develop`.** ¿`develop` renueva la ráfaga (requiere `MQTT_COMANDOS_HABILITADOS=true`) o no?
- **D3 — Cuenta.** Crear `invitado@` como `operador` (la decisión lo pide) con el guard de método, o un rol nuevo de
  solo lectura (cambia el modelo de roles; no lo propongo sin aprobación).

## 7. Fuera de alcance

- Crear la réplica, el usuario de solo lectura y la conexión al broker: DevOps, con autorización del dueño.
- Cualquier cambio en `main` o en producción.
- El rol de solo lectura nuevo (D3), salvo que el dueño lo pida.
