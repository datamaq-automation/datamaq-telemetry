# Ráfaga solo en Wi-Fi y modo de ahorro en 4G

> **Estado:** spec, sin código. Requiere decisiones del dueño (sección 7) antes de implementar.
> **Relacionado:** `specs/rafaga-por-cliente-y-tope.md` (#92), y el incidente `incidentes/2026-10-29_upp-cuota-datos-agotada.md`.
> **Regla del dueño (2026-10-29):** Wi-Fi tiene ráfaga; 4G (chip) no la tiene y el equipo entra en modo de ahorro de datos.

## 1. Objetivo y contexto

La ráfaga (`realtime_sync_mode`, 120 s) hace que el medidor publique cada pocos segundos. Sobre 4G eso consume el
plan de datos del chip: el 29/10 se agotó la cuota de 12 GB de UPP. La regla nueva es: **la ráfaga solo se
permite si el equipo está en Wi-Fi**. Sobre 4G, el equipo queda en modo de ahorro.

Hoy el servidor no sabe por qué medio está conectado cada equipo. La renovación de ráfaga
(`src/application/use_cases/renovar_tiempo_real_medidores.py:28-39`) manda `activar_rafaga` a todos los equipos del
alcance con recepción reciente (`publico_recientemente`, `alcance_tiempo_real.py:12, 53`), sin mirar el medio.

## 2. Qué dice el repo sobre el medio (con fuentes)

| Dato | Fuente | Qué dice |
|---|---|---|
| Keepalive MQTT: 30 s por Wi-Fi, 60 s por 4G | `docs/powermeter_mqtt_protocol.md:24` | Es un parámetro del cliente MQTT del equipo. **No es un campo de payload**: el servidor no lo recibe en ningún tópico. |
| Estructura del tópico `status` | `docs/powermeter_mqtt_protocol.md:125-141` | `wifi_sta: {enabled, connected, quality, dbm, ssid, ip, mac}` y `device_info`. **No hay campo de medio** (ni `4g`, ni `modem`, ni `lte`). |
| Campos que lee el backend de `status` | `src/application/mappers/payload_telemetria_parser.py:379-392` (`parsear_log_estado`) y `src/application/mappers/fase_parser.py:66-69` | Lee `wifi_sta.dbm`, `wifi_sta.quality`, `wifi_sta.ip` y `uptime`. **No lee `connected`, `enabled` ni `ssid`.** |
| Dónde queda guardado | `src/infrastructure/sqlalchemy/models.py` (`DeviceStatusLogModel`, ~líneas 220-232) | Columnas `wifi_rssi_dbm`, `wifi_calidad`, `ip_address`, `uptime_seconds` y `raw_payload` (JSON con el payload completo). `connected` y `ssid` solo quedan dentro de `raw_payload`. |
| Búsqueda de ráfaga y palabras clave "4g/lte/modem" | `git grep` en `origin/develop` | **Ninguna** coincidencia en `src/` de un campo de medio. |

### 2.1 Cadencia observada de `status` (base de desarrollo, solo lectura)

Consulta sobre `datamaq_telemetry` local, solo lectura. Es una copia de desarrollo, no producción.

- `D48C49F03564` (Powermeter-3564): 14 registros, del 2026-09-01 al 2026-09-13.
- `ECC9FFB45488` (Trafo arriba, UPP): 2 registros, 2026-09-11 19:21:40 y 2026-09-12 19:21:41.
- `D48C49F03724` (Trafo abajo, UPP): 2 registros, 2026-09-11 19:22:23 y 2026-09-12 19:22:24.

Los cuatro registros de UPP tienen `wifi_sta.enabled = true` y `connected = true`, con IP `192.168.0.x`. El SSID es
`TP-Link_Extender` en `ECC9FFB45488` y `D926_WINGLE_9E29` en `D48C49F03724`.

**Conclusión:** `status` llega de forma esporádica (un par de veces por día, o menos), no cada 30 o 60 s. Un dato de
medio que dependa de `status` tiene que sobrevivir a días sin mensajes.

**Advertencia importante:** el SSID `WINGLE` sugiere un router 4G que da Wi-Fi a la red local. Si es así,
`wifi_sta.connected = true` **no prueba que el equipo esté sobre Wi-Fi a internet**: podría salir por 4G detrás del
router. El repo no alcanza para decidirlo. Hace falta confirmarlo con el dueño o con DevOps (ver D1).

**Sobre UPP:** el repo no confirma su medio actual. El último `status` local es de 2026-09-12, y el incidente es del
29/10. Con la regla de la sección 3, sin dato reciente UPP queda como 4G por defecto, y eso bloquea la ráfaga. Es la
decisión conservadora correcta, pero no porque el repo confirme que UPP está en 4G.

## 3. Detección del medio por equipo

Propuesta, por capas:

1. **Campo explícito del firmware (preferido, pendiente).** Si el fabricante publica un campo de medio, usarlo.
   No existe en la documentación actual: consultar al proveedor (D1).
2. **Inferencia desde `status` (fallback).** `medio = wifi` solo si el último `status` tiene
   `wifi_sta.enabled = true` **y** `wifi_sta.connected = true`, y es reciente (ver TTL). En cualquier otro caso,
   `medio = 4g`. Esto no distingue Wi-Fi-a-internet de Wi-Fi-a-router-4G (advertencia de la sección 2.1).
3. **Persistencia (no depender de mensajes sueltos).** Guardar en la tabla de dispositivos dos columnas nuevas:
   `medio_conectividad` (`wifi` | `4g` | `desconocido`) y `medio_visto_en` (última vez que se confirmó el medio).
   Cada `status` las actualiza; la lectura de la regla usa solo estas columnas, no el último log. Así, un `status`
   espaciado no cambia el medio hasta que venza el TTL.

### 3.1 TTL del medio (decisión D2)

El TTL es el tiempo que un `medio = wifi` sigue valiendo sin un `status` nuevo. Propuesta: **48 horas**. Con el
volumen observado (un par de mensajes por día), 48 h cubre días normales sin marcar como 4G un equipo que
sigue en Wi-Fi. Vencido el TTL, el medio pasa a `desconocido` y la regla lo trata como 4G.

## 4. Regla por defecto

- Sin dato de medio, o con `medio_visto_en` vencido, o con `medio = 4g`: **se trata como 4G**.
- Solo `medio = wifi` y vigente: permitido.

Es la regla conservadora para el chip: un error de detección cuesta ráfaga, no datos.

## 5. Ráfaga

- `renovar_tiempo_real_medidores.py` solo manda `activar_rafaga` a equipos con `medio = wifi` vigente, y dentro de la
  organización del usuario (la limitación de #99, que sigue abierta).
- El tope por minuto de #92 se mantiene sin cambios.
- La respuesta de `POST /api/v1/dispositivos/{id}/realtime` para un equipo en 4G: propuesta **409 Conflict** con
  `detail: "ráfaga_no_permitida_en_4g"` (decisión D3). No es 403: el 403 queda para el rol `solo_lectura`.

## 6. Modo de ahorro en 4G

Qué cambia en 4G, dos niveles:

**Del lado del servidor (no necesita comandos al equipo):**
- No se envía ráfaga (sección 5).
- No se emiten comandos a `conf/com` por el backend para ese equipo (la compuerta `publicar_comando` ya existe,
  `mqtt_listener.py`).

**Del lado del equipo (necesita `conf/com`):**
- Cadencia de `inst`: hoy 300 s de fábrica (`docs/powermeter_mqtt_protocol.md:53`). Propuesta: mantener 300 s; no
  bajarla.
- Cadencia de `status`: no está documentada como configurable. Propuesta: no tocarla hasta confirmar con el fabricante.

Valores propuestos, todos sujetos a D4:

| Parámetro | Wi-Fi | 4G (ahorro) |
|---|---|---|
| Ráfaga | permitida (con límite de #92 y organización de #99) | no |
| Cadencia `inst` | 300 s (fábrica) | 300 s (sin cambio: el servidor ya no pide ráfaga) |
| Renovación automática | sí | no |

## 7. ¿Hace falta enviar comandos al equipo?

**Respuesta propuesta: el ahorro se puede definir solo del lado del servidor** para lo que el servidor controla: no pedir
ráfaga y no mandar comandos a 4G. Eso ya reduce el consumo que pidió el dueño.

Un cambio de modo **en el equipo** (cadencia, apagar publicaciones) sí requiere `conf/com`. Eso está apagado en `api-dev`
(`MQTT_COMANDOS_HABILITADOS=false`) y no se activa sin decisión del dueño (D4).

## 8. Criterios de prueba

| Caso | Resultado esperado |
|---|---|
| Equipo con `medio = wifi` vigente, dentro de la organización | Ráfaga enviada (`activar_rafaga` llamado) |
| Equipo con `medio = 4g` | Ráfaga no enviada; respuesta 409 con `ráfaga_no_permitida_en_4g` |
| Equipo sin ningún `status` | Tratado como 4G (no envía ráfaga) |
| `status` con `connected = true` hace más de TTL | Tratado como 4G |
| `status` nuevo con `connected = false` | `medio = 4g` |
| Equipo en Wi-Fi de otra organización | Sigue la regla de #99 (404) |
| Superadmin sobre equipo en 4G | 409 también (la regla de medio no depende del rol) |

Pruebas de dominio para la regla (`medio` + TTL), de aplicación para la renovación, e integración para la persistencia
de `medio_visto_en`.

## 9. Decisiones del dueño (no decididas)

- **D1 — Fuente del medio.** ¿El fabricante puede publicar un campo explícito de medio (wifi/4g)? ¿Y el SSID `WINGLE`:
  el equipo sale a internet por Wi-Fi o por el 4G detrás de ese router? Sin esa respuesta, la inferencia de la
  sección 3 puede marcar 4G a un equipo que está en Wi-Fi, o al revés.
- **D2 — TTL.** Propuesta 48 h. ¿Otro valor?
- **D3 — Respuesta en 4G.** Propuesta 409 con motivo. ¿Prefiere otro código?
- **D4 — Ahorro en el equipo.** ¿Solo servidor (propuesta) o también comandos `conf/com` para cambiar el equipo? Si es
  lo segundo, requiere autorización explícita y `MQTT_COMANDOS_HABILITADOS` en `true` en el ambiente que corresponda.
- **D5 — Estado de UPP.** Confirmar con DevOps o con el dueño el medio actual de `ECC9FFB45488` y `D48C49F03724`. El
  repo no lo confirma: el último `status` local es de 2026-09-12.
- **D6 — Cuándo.** Esta regla se activa con el release de telemetry a `main`, que el dueño decide, o antes en `develop`.

## 10. Fuera de alcance

- Cambiar el firmware o el plan de datos del chip.
- Cambiar la cadencia permanente de `inst` (300 s).
- Alertas de cuota (issue aparte).
