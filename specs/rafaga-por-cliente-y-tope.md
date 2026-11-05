# Renovación de ráfaga por cliente y con tope por minuto

> **Issue:** datamaq-automation/datamaq-telemetry#92 · **Rama de la spec:** `docs/spec-issue-92-rafaga`
> **Estado:** spec, sin código. Requiere decisiones del dueño (sección 7) antes de implementar.
> **Relacionado:** `specs/renovacion-tiempo-real-acotada.md` (issue #15, ya implementado: renueva solo el alcance conectado).

## 1. Objetivo y Contexto

La ráfaga (`realtime_sync_mode`, 120 s) hace que los medidores publiquen cada pocos segundos. La renovación la
dispara el servidor mientras haya un cliente WebSocket conectado. Hoy el alcance es **la organización completa**
del cliente, no el equipo que mira, y no hay tope: un cliente que se reconecta en bucle dispara una renovación por
cada conexión.

Dónde está hoy (verificado en `origin/develop`):

- **Alcance por organización.** `src/domain/telemetria/servicios/alcance_tiempo_real.py:38-47`: `alcance_de_clientes`
  arma el alcance con `(es_superadmin, organizacion_id)` de cada cliente. Un superadmin da `todas=True`.
- **Renovación con el alcance completo.** `src/application/use_cases/renovar_tiempo_real_medidores.py:28-43`:
  `ejecutar` recorre **todos los dispositivos del alcance** (`_dispositivos_del_alcance`, líneas 41-43). Por cada uno
  con recepción reciente (`publico_recientemente`, ventana `VENTANA_RECEPCION_RECIENTE_S = 600`,
  `alcance_tiempo_real.py:12`) llama `activar_rafaga(uid, 120)` (`renovar_tiempo_real_medidores.py:14, 37`).
- **Disparo por heartbeat.** `src/infrastructure/fastapi/server.py:301-329` (`_ws_heartbeat_loop`): cada 25 s, si hay
  clientes conectados y la marca venció (`INTERVALO_RENOVACION_S = 60`, `renovacion_tiempo_real.py:21`), renueva con
  `list(active_websockets)` (línea 323). El alcance sale de `_renovar_modo_tiempo_real_medidores`
  (`server.py:245-248`).
- **Disparo por conexión.** `server.py:429-448` `_registrar_cliente_ws`: al conectarse un cliente, si su
  alcance no lo cubre el alcance previo, renueva **sin tope**. La marca se registra solo si el nuevo alcance cubre
  al previo (línea 448). Un cliente que se reconecta en bucle y no pasa esa condición dispara una renovación por
  conexión.
- **El servidor no sabe qué mira el cliente.** `server.py:451-456` `_bucle_recepcion_ws` solo procesa
  `ping`. No hay mensaje de suscripción: el WebSocket no transmite a qué dispositivos se suscribió la vista.

Incidente de referencia: `incidentes/2026-10-29_upp-cuota-datos-agotada.md`. Según el issue, el 29/10 se publicaron
779 comandos a todas las MACs y dos equipos de UPP quedaron en ráfaga de 10:10 a 10:54. Esa cifra viene del issue y
del incidente; no la volví a verificar en logs.

## 2. Qué se renueva y cuándo

Regla propuesta:

1. **Solo los dispositivos que el cliente tiene abiertos** en la vista en vivo. Un dispositivo entra al alcance
   cuando el cliente se suscribe y sale cuando se desuscribe o se desconecta.
2. **Cadencia.** La renovación periódica sigue en 60 s (`INTERVALO_RENOVACION_S`), con el mismo tick del heartbeat.
   No cambia la duración de 120 s ni la cadencia permanente de los equipos (fuera de alcance del issue).
3. **Al suscribirse** un cliente a un dispositivo que nadie tenía abierto, se renueva ese dispositivo de inmediato
   (el mismo criterio que `_registrar_cliente_ws`), sujeto al tope de la sección 3.
4. **Al desconectarse** un cliente, el dispositivo deja de renovarse. La ráfaga vence sola a los 120 s; no se manda
   ningún comando de parada.
5. **Dispositivos sin recepción reciente** (`publico_recientemente`, 600 s) siguen omitiéndose, como hoy.

## 3. Tope por minuto

Propuesta: **N = 2 renovaciones por dispositivo y por minuto de ventana deslizante**, contadas en el servidor.

Justificación:

- En régimen, la renovación periódica da 1 por minuto por dispositivo (`INTERVALO_RENOVACION_S = 60`). Con N = 1, un
  cliente que se suscribe justo después del tick no se renueva hasta el siguiente, es decir hasta ~60 s después.
- Con N = 2 cabe la renovación del tick y una renovación por suscripción o reconexión dentro del mismo minuto. Un
  bucle de reconexiones no pasa de 2 por minuto por dispositivo, que es lo que pide el criterio del issue.
- El tope es por dispositivo y no por cliente, porque el costo está en el equipo (el chip), no en la conexión.

**Esto es una propuesta. El valor de N lo decide el dueño** (sección 7, decisión D2).

Comportamiento al llegar al tope: el comando **no se envía** y se registra un log `realtime_renovacion_limitada`
con el UID y el motivo (`heartbeat`, `suscripcion`, `conexion`). La próxima renovación del tick igual se intenta, y
si el tope sigue lleno se omite. La ventana es en memoria del proceso: supone un solo proceso, como el listener MQTT
(ver `specs/renovacion-tiempo-real-acotada.md`).

## 4. Comportamiento de la vista en vivo

El cliente tiene que decir qué mira. Propuesta de protocolo, mínima:

- Mensaje entrante `{"type": "subscribe", "device_uids": ["ECC9FFB45488", ...]}`: reemplaza la suscripción anterior
  de esa conexión.
- Mensaje entrante `{"type": "unsubscribe"}`: vacía la suscripción.
- Sin mensaje de suscripción, la conexión **no suma alcance de equipos** (no renueva nada). Esta es la decisión D1: si
  eso rompe la vista actual, hace falta un período de transición en el que el alcance por organización siga vigente.

El frontend (`app-datamaq`) tendría que enviar `subscribe` al abrir y al cambiar de equipo. Ese cambio es de la app,
no de este repo, y se coordina por la matriz de compatibilidad (`docs/matriz-compatibilidad-frontend.md`).

## 5. Casos de borde

| Caso | Comportamiento propuesto |
|---|---|
| Reconexión en bucle (el cliente cae y vuelve cada pocos segundos) | Cada conexión re-suscribe; el tope de la sección 3 corta las renovaciones por minuto. Se registra `realtime_renovacion_limitada`. |
| Cliente que cierra sin aviso (pestaña cerrada, red caída) | El servidor lo detecta al fallar el envío del heartbeat o al cerrarse el WebSocket. Se quita de la suscripción. La ráfaga vence sola a los 120 s. |
| Dos clientes sobre el mismo equipo | El alcance es la unión. El equipo se renueva **una vez por tick**, no una por cliente. Si uno se desconecta y el otro sigue, el equipo sigue en el alcance. |
| Cliente sin suscripción (mensaje no enviado o frontend viejo) | No renueva equipos. Ver D1. |
| Superadmin | Hoy `todas=True` renueva toda la base. Con esta spec, el superadmin renueva solo lo suscripto. Ver D3. |
| Equipo sin recepción reciente | Se omite, como hoy (`publico_recientemente`). |
| Fallo de `activar_rafaga` para un equipo | No corta la renovación de los demás (como hoy en `ejecutar`); se cuenta y se loguea. |

## 6. Criterios de aceptación y pruebas

Criterios (del issue, más los de esta spec):

- Con un cliente abierto sobre un dispositivo, **solo ese dispositivo** recibe renovaciones.
- Reconexiones en bucle **no superan N renovaciones por minuto por dispositivo**.
- Un dispositivo con dos clientes se renueva una vez por tick.
- Un log por renovación, con su motivo; un log por cada renovación omitida por tope.
- Tests de aplicación y de infraestructura. Gauntlet local verde.
- PR de 400 a 500 líneas contra `develop`, commits atómicos por capa.

Matriz de pruebas (RED primero):

| Prueba | Capa | Verifica |
|---|---|---|
| `test_alcance_solo_suscripto` | dominio | con suscripción a A, el alcance contiene A y no B |
| `test_union_de_suscripciones_sin_duplicar` | dominio | dos clientes sobre A dan un solo A en el alcance |
| `test_tope_por_minuto_ventana_deslizante` | dominio | N+1 renovaciones en 60 s: solo N pasan |
| `test_renovacion_solo_de_suscriptos` | aplicación | `RenovarTiempoRealMedidoresUseCase` con alcance suscripto |
| `test_reconexion_en_bucle_respeta_tope` | aplicación | 10 suscripciones en 60 s sobre A: como máximo N comandos |
| `test_subscribe_entrante_actualiza_alcance` | infra (WS) | mensaje `subscribe` cambia el alcance de la conexión |
| `test_cliente_que_cierra_quita_alcance` | infra (WS) | desconexión saca el equipo del alcance |
| `test_log_de_renovacion_limitada` | infra | el log se emite con UID y motivo |

## 7. Decisiones del dueño (no decididas en esta spec)

- **D1 — Compatibilidad sin suscripción.** ¿Una conexión sin `subscribe` renueva nada (corte duro) o conserva el
  alcance por organización durante una transición? La segunda opción mantiene la ráfaga mientras el frontend no
  migra, y es la que sigue consumiendo cuota.
- **D2 — Valor de N.** Propuesta: 2 por minuto por dispositivo. Alternativa: 1 (más estricto, pero el primer
  cliente puede esperar hasta 60 s).
- **D3 — Superadmin.** ¿El superadmin renueva solo lo que abre, o toda la base como hoy? Ver también el riesgo
  de cuota si hay un superadmin con la app abierta.
- **D4 — Vista de planta vs. vista de equipo.** Si la vista de planta abre 10 equipos a la vez, ¿se renuevan los 10?
  Con N = 2 por minuto, son 10 comandos por minuto. ¿Está bien ese costo para la cuota?
- **D5 — Frontend.** El cambio del frontend para enviar `subscribe` es de `app-datamaq`. ¿Se hace en el mismo release
  o en uno posterior? Se coordina con la matriz de compatibilidad.

## 8. Fuera de alcance

- Cambiar la duración de 120 s o la cadencia permanente de los equipos.
- La campaña de caracterización de cargas (`caracterizar_carga.py`), salvo que su renovación use el mismo camino.
- El ACL de Mosquitto y la alerta de cuota: son issues aparte.
