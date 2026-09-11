# Plan: conectar el medidor SmartPlus de Vajillas Durax al servidor Datamaq

## Contexto

Durante la sesión del 2026-09-10 se investigó por qué el usuario `instrumental@vajillasdurax.com.ar`
tenía un dispositivo seleccionable en el portal sin ningún dato. Diagnóstico confirmado contra la
base de producción:

- Dispositivo: `F8B3B7C0BBB0` ("SmartPlus Trifásico #1"), planta "Planta Principal Durax",
  organización "Vajillas Durax S.A." — creado el 2026-09-10 vía `scripts/seed_cliente.py`.
- **Cero filas** en `telemetry_instantaneous` y `telemetry_energy` para ese `device_id`.
- El broker Mosquitto nunca registró una conexión real del equipo (`New client connected ...
  as F8B3B7C0BBB0` no aparece en `/var/log/mosquitto/mosquitto.log`).
- El estado `ONLINE` / `last_seen_at` que mostraba el portal era un **falso positivo** de software
  (el backend se marcaba a sí mismo "visto" por el eco de sus propios comandos salientes
  `conf/com`) — ya corregido y desplegado en el commit `5b6211b` (ver
  `tests/unit/test_mqtt_eco_comando_propio.py`). Con ese fix, el estado dejará de avanzar
  artificialmente y reflejará la realidad: el equipo sigue sin conectarse.

**Conclusión: el medidor físico de Vajillas Durax nunca se conectó al broker MQTT de producción.**
No es un bug de software — es un problema de aprovisionamiento del equipo en la planta del cliente,
igual al que se resolvió al principio de esta misma sesión con el medidor doméstico
(`D48C49F03564`, ver commit del cambio de servidor de `mqtt.powermeter.com.ar` a
`mqtt.datamaq.com.ar` desde el portal de configuración local del equipo).

## Objetivo

Conectar el medidor de Vajillas Durax al servidor propio (`mqtt.datamaq.com.ar:8883`) siguiendo
el mismo procedimiento ya documentado y probado en
[`docs/provisioning_guide.md`](./provisioning_guide.md), y verificar que empiece a reportar
telemetría real.

## Pre-requisito operativo

Hay que estar físicamente conectado a la red Wi-Fi donde vive el medidor:

- Si el equipo está en modo fábrica (nunca aprovisionado): su propio AP `Powermeter-<MAC>`,
  gateway `192.168.4.1`.
- Si ya fue unido a la red Wi-Fi de la planta de Durax: esa red, y hay que ubicar su IP por DHCP
  (ver §3.2 de [`docs/troubleshooting-conectividad-dispositivos.md`](./troubleshooting-conectividad-dispositivos.md),
  barrido ARP + escaneo de puerto 80).

Confirmar la red activa antes de cada paso con:

```bash
nmcli -t -f active,ssid dev wifi 2>/dev/null | grep '^yes' || iwgetid -r
```

## Plan de ejecución

### 1. Confirmar conectividad de red y ubicar el equipo

- `nmcli`/`iwgetid` para confirmar la red activa (ver arriba).
- Barrido de ping + escaneo del puerto 80 (servidor web del ESP32) en la subred, igual que se
  hizo con el medidor doméstico al inicio de esta sesión.
- Confirmar identidad del equipo por su interfaz web (`http://<ip>/`, tema `powermeter`,
  color `#04C4A4`) antes de tocar nada.

### 2. Aprovisionar el broker Datamaq

**Preferido — Método 1 automatizado** (`docs/provisioning_guide.md`, §"Método 1"):

```bash
export MQTT_PASSWORD='<contraseña de datamaq_device, en .env del VPS>'
python3 scripts/provision_device.py --profile datamaq --reboot
```

El script valida la configuración antes de enviarla (rechaza puerto 1883, TLS sin CA, credenciales
faltantes) — más seguro que cargarlo a mano.

**Alternativa manual** (si el equipo no responde a la API del script): Método 2 de la misma guía,
vía `http://<ip>/home.html` (usuario `admin` / contraseña `powermeter`), sección MQTT:

| Parámetro | Valor |
|---|---|
| Broker Host | `mqtt.datamaq.com.ar` |
| Puerto | `8883` |
| Seguridad | `TLS-SERVER-AUTH` |
| CA | contenido de `isrg_root_x1.pem` (repo, raíz) |
| Usuario | `datamaq_device` |
| Contraseña | `MQTT_PASSWORD` del `.env` de producción |
| Client ID | `F8B3B7C0BBB0` |

> [!WARNING]
> No dejar el campo de CA vacío al guardar si el equipo ya tenía uno cargado — lo borra y rompe
> el TLS (ver nota en `provisioning_guide.md`).

### 3. Auditar credenciales Wi-Fi si el equipo no se asocia

Si tras aprovisionar el equipo no aparece conectado, correr:

```bash
python3 scripts/provision_device.py --wifi-audit
```

Para descartar el incidente ya documentado del 2026-09-01 (homóglifos no-ASCII en SSID/contraseña
que producen un PSK distinto sin ningún error visible).

### 4. Verificar desde el servidor (vía `ssh vps`)

```bash
./scripts/logs.sh --mqtt --device F8B3B7C0BBB0
```

Confirmar en el broker una línea `New client connected ... as F8B3B7C0BBB0` (no solo el eco de
comandos salientes del backend), y en la app logs de `mqtt_mensaje_recibido` con tópicos `inst`,
`acc`, `energyio` reales — no solo `conf/com`/`conf/rta`.

### 5. Verificar en la base de datos

Confirmar filas nuevas en `telemetry_instantaneous`/`telemetry_energy` para el `device_id`
`51048a93-f1f3-4283-a708-24cbd39c7192` (o filtrando por `device_uid = 'F8B3B7C0BBB0'`).

### 6. Verificación end-to-end en el portal

Con `instrumental@vajillasdurax.com.ar`: seleccionar el dispositivo y confirmar que el monitor en
vivo muestra potencia real (no cero, no "sin datos").

## Notas

- El aislamiento multi-tenant (WebSocket + REST, commits `5f3db32` y `a1f6870`) ya garantiza que
  este usuario solo vea este dispositivo — no hace falta ningún cambio adicional de permisos una
  vez que el equipo esté transmitiendo.
- Este documento es un plan operativo/de campo, no requiere cambios de código — si en el proceso
  aparece un bug de software nuevo, documentarlo aparte (ver convención de
  `docs/troubleshooting-conectividad-dispositivos.md` §4, "Incidente ...").
