# Renovación de tiempo real acotada y sin eco

> **Issue:** datamaq-automation/datamaq#15 · **Rama:** `fix/issue-15-renovacion-tiempo-real-acotada`
> **Spec del padre:** `specs/thd-descartes-observables-y-renovacion-tiempo-real.md` (bloque B)

## 1. Objetivo y Contexto

La renovación de `realtime_sync_mode` tiene que alcanzar solo a los medidores que algún cliente conectado puede ver.
Además, el worker no tiene que procesar ni loguear en INFO el eco de sus propios comandos.

Auditoría del VPS del 2026-10-11 (commit `089f2ef`): `_ws_heartbeat_loop` revisa cada 25 s y, si pasaron ≥ 60 s y hay
**al menos un** WebSocket, llama a `_renovar_modo_tiempo_real_medidores`. Esa función mandaba `realtime_sync_mode`
(`time_s: 120`) a **todos** los dispositivos de `devices`, sin mirar organización ni estado: 476 comandos a 7 medidores
en ~100 min. El worker se suscribe a `m/wifi/#`, así que recibía el eco (`…/conf/com`) y lo logueaba como
`mqtt_mensaje_recibido`. El heartbeat terminaba en `except Exception: pass`.

**Fuera de alcance:** suscripción por dispositivo en el WebSocket, `time_s: 120`, el intervalo de 60 s y
`_loop_campanas_activas`.

## 2. Dominio & Puertos

`src/domain/telemetria/servicios/alcance_tiempo_real.py` (solo stdlib):

- `AlcanceTiempoReal(todas, organizaciones)`: `todas=True` si hay un superadmin conectado. `vacio` y `cubre(otro)`.
- `alcance_de_clientes(pares (es_superadmin, organizacion_id))`: un cliente sin organización que no es superadmin no
  aporta nada, igual que en `debe_recibir_evento`.
- `publico_recientemente(visto_por_ultima_vez, ahora, ventana_s=600)`: `None` (nunca publicó) da False.

**Dato de última recepción (punto 2 del padre):** ya existe. `Dispositivo.visto_por_ultima_vez` (`devices.last_seen_at`,
UTC aware por `UtcDateTime`) se actualiza como mucho cada 60 s mientras el medidor publica
(`ResolvedorDispositivoIngesta.obtener_o_crear_dispositivo`). No se creó nada nuevo.

Puertos reutilizados: `RepositorioDispositivosPort.listar(organizacion_id=...)` (filtra por la organización de la
planta) y `ComandoRafagaPort.activar_rafaga` (`MqttComandoRafagaGateway`).

## 3. Caso de uso & DTOs

`RenovarTiempoRealMedidoresUseCase.ejecutar(alcance, ahora) -> ResultadoRenovacionTiempoReal(renovados,
omitidos_sin_recepcion_reciente)` (`src/application/use_cases/renovar_tiempo_real_medidores.py`):

1. Alcance `todas` → `listar()`. Si no, `listar(organizacion_id=o)` por cada organización, deduplicado por id.
2. Omite los dispositivos sin `device_uid` y los que no publicaron en 600 s.
3. `activar_rafaga(uid, 120)`; cuenta como renovado solo si el comando se publicó.

Infraestructura:

- `server._renovar_modo_tiempo_real_medidores(listener, clientes)`: con alcance vacío no abre sesión. Loguea
  `realtime_mode_auto_renovado` con `total_dispositivos` (renovados), `omitidos_sin_recepcion_reciente` y
  `organizaciones` (`"todas"` o la lista).
- `_ws_heartbeat_loop` renueva con `active_websockets` y, ante un error, loguea `ws_heartbeat_fallido` en WARNING.
- **Ajuste aprobado por el padre:** `_registrar_cliente_ws` renovaba solo con el primer cliente. Ahora renueva el
  alcance del cliente nuevo si el alcance previo no lo cubría. Sin esto, un cliente de otra organización que se conecta
  con otro ya conectado esperaría hasta ~85 s al heartbeat.
- `MQTTListener._on_message` descarta `…/conf/com` antes de loguear, deduplicar o abrir sesión de base:
  `mqtt_eco_comando_propio_descartado` en DEBUG. El envío ya queda como `mqtt_comando_publicado`. El filtro que tenía
  `IngestarTelemetriaUseCase` para `conf/com` queda como defensa.

## 4. Matriz de Pruebas (RED Suite)

| Archivo | Tests |
|---|---|
| `test_alcance_tiempo_real.py` | alcance vacío, unión de organizaciones, superadmin = todas, cliente sin organización, `cubre`, ventana 600/601 s, `None` |
| `test_renovar_tiempo_real_medidores.py` | solo la organización conectada y en línea; superadmin = todos (incluso sin planta); sin duplicados entre organizaciones; alcance vacío no consulta; comando fallido no cuenta |
| `test_realtime_command.py` | superadmin → `listar()`; organización → `listar(organizacion_id=...)`; sin alcance no abre sesión; registro: primer cliente, organización ya cubierta, otra organización, superadmin conectado, superadmin que llega después; heartbeat loguea `ws_heartbeat_fallido` |
| `test_mqtt_eco_comando_propio.py` | `conf/com` no llega al executor ni loguea INFO; `conf/rta` sí se procesa |

## 5. Criterios del Gauntlet

`./scripts/pre-push.sh` en verde (con `APP_ENV=test`, como CI): arquitectura, tamaño (`server.py` 526/550 líneas), ruff,
pyright y tests unitarios con cobertura ≥ 85 %.

## 6. Notas de implementación

- **Renovación doble al conectarse (agregado 2026-10-11, último comentario de #15):** en producción hubo dos
  `realtime_mode_auto_renovado` separados por 1,4 s (4 de 137 desde el 09/10). `_registrar_cliente_ws` renovaba, pero
  `ultimo_sync_realtime` era una variable local de `_ws_heartbeat_loop` y quedaba vieja mientras no había clientes.
  Ahora la renovación y una marca compartida (`MarcaRenovacion`, intervalo 60 s) viven en
  `src/infrastructure/fastapi/renovacion_tiempo_real.py`, y los dos caminos la usan. La conexión **solo corre la marca
  si renovó todo el alcance conectado** (primer cliente o superadmin). Si un cliente de otra organización la corriera,
  las organizaciones ya conectadas podrían pasar 60 + 25 s + el desfase sin renovar, más que los 120 s de `time_s`.
  Para la organización nueva, una renovación de más en el siguiente tick es inofensiva. Tests en
  `test_realtime_command.py`: primer tick sin repetir, tick con la marca vencida, otra organización no corre la marca,
  y un superadmin que llega después sí la corre.
- `server.py` bajó de 541 a 526 líneas (límite 550): la renovación salió a su propio módulo.
- Verificación en producción (la hace el padre): con un cliente que no es superadmin conectado,
  `realtime_mode_auto_renovado` informa solo los dispositivos de su organización, y no aparece `mqtt_mensaje_recibido`
  para `conf/com`.
