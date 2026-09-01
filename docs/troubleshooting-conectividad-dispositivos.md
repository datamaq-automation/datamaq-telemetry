# Troubleshooting de Conectividad de Medidores Powermeter

> **Propósito:** contestar de forma determinística la pregunta *"el medidor no reporta: ¿falló el
> Wi-Fi o falló el servidor?"*, y dejar registrado el incidente del **2026-09-01** con toda la
> evidencia recolectada, para no repetir el diagnóstico desde cero.

---

## 1. Datos de infraestructura (necesarios para diagnosticar)

| Recurso | Valor |
|---|---|
| Acceso al VPS | `ssh vps` (alias en `~/.ssh/config`, HostName IPv6) |
| Ruta de despliegue | `/var/www/datamaq-telemetry` (su `.env` tiene las credenciales reales) |
| Servicio backend | `datamaq-telemetry.service` (uvicorn en `127.0.0.1:8000`) |
| Broker | `mosquitto.service`, config en `/etc/mosquitto/conf.d/datamaq.conf` |
| **Log del broker** | **`/var/log/mosquitto/mosquitto.log` (archivo, NO journald)** |
| Listeners | `1883` solo en `127.0.0.1` · `8883` en `0.0.0.0` (TLS) |
| Auth del broker | `allow_anonymous false`, único usuario: `datamaq_device` |
| Certificado | Let's Encrypt `CN=mqtt.datamaq.com.ar`, cadena valida contra **ISRG Root X1** |
| DNS | `mqtt.datamaq.com.ar` → `168.181.184.103` |
| Base de datos | MySQL `datamaq_telemetry`, tablas `devices` y `telemetry_instantaneous` |

> [!NOTE]
> `journalctl -u mosquitto` devuelve **"No entries"** porque el broker usa `log_dest file`.
> Esto hizo perder tiempo en el incidente: `scripts/logs.sh --mqtt` fue corregido para leer el
> archivo. Nunca concluyas "no hay actividad" mirando journald.

---

## 2. Árbol de decisión

El punto clave: **el log del broker separa las dos causas de forma limpia.**

```
¿Hay alguna línea "New connection from <IP pública del sitio>" en mosquitto.log?
├── SÍ  → el equipo llegó al servidor. El Wi-Fi funciona. Falla la capa MQTT:
│         · "Socket error ... OpenSSL Error"      → CA / TLS mal configurado en el equipo
│         · "Client ... not authorised"           → usuario o contraseña MQTT incorrectos
│         · conecta y luego "exceeded timeout"    → señal Wi-Fi débil / equipo se cuelga
└── NO  → el equipo NUNCA abrió un socket. Confirmarlo con el barrido de LAN (§3.2):
          · no aparece en la LAN → no se asoció al Wi-Fi (causa más probable)
          · aparece en la LAN    → tiene IP pero no sale a internet, o apunta a otro broker
```

Ignorar el ruido de fondo: el `8883` recibe escaneo constante de internet
(`195.96.139.x`, `87.236.176.x`, `185.247.137.x`, `66.132.x.x`). Se reconocen porque el cliente
es `<unknown>` y nunca llegan a `New client connected`.

---

## 3. Playbook de comandos

### 3.1 Lado servidor

```bash
# Eventos de medidores reales, sin escáneres
./scripts/logs.sh --mqtt --device
./scripts/logs.sh --mqtt --device D48C49F03564      # un equipo puntual
./scripts/logs.sh --mqtt -f                          # en vivo mientras se reintenta

# Salud del broker y listeners
ssh vps "systemctl is-active mosquitto; ss -ltnp | grep -E '1883|8883'"
ssh vps "grep -vE '^\s*#|^\s*$' /etc/mosquitto/conf.d/datamaq.conf"

# Último dato persistido por equipo
ssh vps "cd /var/www/datamaq-telemetry && \
  mysql -u\$(grep ^DB_USER= .env|cut -d= -f2-) -p\$(grep ^DB_PASSWORD= .env|cut -d= -f2-) \
  \$(grep ^DB_NAME= .env|cut -d= -f2-) \
  -e \"SELECT device_uid,model,fw_version,status,last_seen_at FROM devices;\""
```

Las marcas de tiempo del log de Mosquitto son **epoch**: `date -d @1787447982`.

### 3.2 Lado red local (desde una máquina en la misma LAN que el medidor)

```bash
# IP pública del sitio: es la que hay que buscar en el log del broker
curl -s -4 https://ifconfig.me

# ¿El medidor tomó IP por DHCP? Barrido ARP + escaneo del puerto 80 (el ESP32 sirve su web)
for i in $(seq 1 254); do (ping -c2 -i0.3 -W1 192.168.0.$i >/dev/null 2>&1 &); done; sleep 8
ip neigh show | grep -v FAILED
for i in $(seq 1 254); do (timeout 2 bash -c "</dev/tcp/192.168.0.$i/80" 2>/dev/null \
  && echo "192.168.0.$i:80"); done
```

### 3.3 Prueba de extremo a extremo (descarta el servidor en 10 segundos)

Simula al medidor desde la misma red del sitio: DNS + TCP + TLS + auth + publish.

```bash
export MQTT_PASSWORD=$(ssh vps "grep ^MQTT_PASSWORD= /var/www/datamaq-telemetry/.env | cut -d= -f2-")
mosquitto_pub -h mqtt.datamaq.com.ar -p 8883 --cafile isrg_root_x1.pem \
  -u datamaq_device -P "$MQTT_PASSWORD" \
  -i TEST-DIAG-LAN -q 1 -k 30 -t 'm/wifi/TESTDIAG/status' -m '{"diag":1}' -d
```

`received CONNACK (0)` + `received PUBACK` ⇒ **el servidor y la ruta de red están sanos**; el
problema es del equipo.

### 3.4 Lado equipo (el chequeo definitivo)

Si el equipo no logró asociarse, cae a **modo AP** publicando el SSID `Powermeter-<MAC>`.
Que ese SSID sea visible ya es prueba de que el Wi-Fi falló.

```bash
# Conectado a la red del equipo (gateway 192.168.4.1)
python3 scripts/provision_device.py --status
```

Imprime `wifi_sta.connected`, `wifi_sta.quality`, `mqtt.connected` y un veredicto explícito.
Equivale a `GET http://192.168.4.1/status.json` con Basic Auth `admin:powermeter`, que se puede
abrir desde el navegador de un celular.

---

## 4. Incidente 2026-09-01 — "el medidor no termina de conectarse"

### Síntoma reportado
Se conectó un Powermeter SmartPlus a la red Wi-Fi del sitio y no llegaba a reportar. No se sabía
si había fallado el Wi-Fi o la conexión al servidor.

### Evidencia recolectada

**Servidor: sano.** `mosquitto` y `datamaq-telemetry.service` activos; `8883` escuchando en
`0.0.0.0` y alcanzable desde la LAN del sitio; DNS correcto; certificado válido hasta el
**2026-11-16**; firewall en `policy accept`. La prueba de §3.3 desde la IP del sitio
(`181.46.69.159`) devolvió `CONNACK (0)` + `PUBACK`.

**Equipo: ausente de toda la ruta.**
- Cero líneas `New connection from 181.46.69.159` en `mosquitto.log` ese día. Lo único que llegó
  al `8883` fueron escáneres de internet.
- Barrido completo de `192.168.0.0/24`: solo 4 hosts vivos (router `.1` más `.2`, `.3`, `.4`),
  ningún servidor web salvo el router y la PC de trabajo. **El medidor no tomó IP por DHCP.**

**Historial del equipo `D48C49F03564`** (SmartPlus, FW `V1.3.0`, `Powermeter-3564`):

| Conexión | Duración | Cómo terminó |
|---|---|---|
| 2026-08-18 01:42 | ~8 h | `Socket error` |
| 2026-08-18 09:57 | ~18 min | `exceeded timeout` |
| 2026-08-20 20:59 (desde `186.143.195.22`) | ~28 min | `exceeded timeout` |
| **2026-08-22 22:19** | ~48 min | `exceeded timeout` ← última conexión registrada |

En MySQL: `last_seen_at = 2026-08-23 02:05`, 116 filas en `telemetry_instantaneous`,
última del `2026-08-23 01:50`.

### Conclusión

**El equipo no se asoció al Wi-Fi.** Si se hubiera asociado y sólo fallara MQTT, aparecería en la
LAN con IP, o el intento (aunque rechazado por TLS/credenciales) figuraría en el log del broker.
No ocurrió ninguna de las dos cosas.

Como causa secundaria, el patrón histórico —sesiones de 20-50 min que **siempre** mueren por
keepalive vencido y **nunca** reconectan solas— apunta a señal Wi-Fi débil en el punto de
instalación o a un cuelgue del stack Wi-Fi del ESP32, no a un problema de broker.

### Pendiente de confirmar en sitio

1. Desde un celular, buscar el SSID `Powermeter-D48C49F03564`. Si aparece → confirmado que no
   entró al Wi-Fi.
2. Conectarse a ese AP y correr `provision_device.py --status` (o abrir
   `http://192.168.4.1/status.json`) para leer `wifi_sta.quality` y confirmar la señal.
3. Verificar que la red destino sea **2.4 GHz WPA2**: el ESP32 no soporta 5 GHz ni WPA3-only, y
   falla si el router unifica ambas bandas en un mismo SSID (*band steering*).
4. Revisar la ubicación del equipo en el tablero: la señal baja explicaría las caídas por
   keepalive del historial.

---

## 5. Deuda corregida a raíz de este incidente

| Problema | Estado |
|---|---|
| `docs/provisioning_guide.md` indicaba `1883` / `NO-SECURITY` / usuario vacío — imposible de conectar | Corregido |
| `profiles/datamaq_server.json` con `username`/`password` vacíos y sin CA | Corregido (usuario fijo + CA por referencia) |
| `provision_device.py` hacía POST del CA aunque estuviera vacío, **borrando el CA del equipo** | Corregido (omite el POST si no hay CA) |
| `provision_device.py` no validaba nada antes de escribir en el equipo | Corregido (`_validar_config`) |
| `provision_device.py --status` no emitía veredicto Wi-Fi vs MQTT | Corregido (`_diagnosticar`) |
| `provision_device.py` devolvía exit 0 aunque fallara | Corregido |
| `logs.sh --mqtt` usaba journald ⇒ siempre "No entries" | Corregido (lee el archivo) |
| `logs.sh --status` buscaba el puerto inexistente `8885` | Corregido a `8883` |
| `isrg_root_x1.pem` estaba en `.gitignore` pese a ser una CA raíz pública necesaria para aprovisionar | Versionado |
