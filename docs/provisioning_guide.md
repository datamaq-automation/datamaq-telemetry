# Guía de Aprovisionamiento de Medidores Powermeter para Clientes Datamaq

Esta guía explica cómo configurar los medidores de energía **Powermeter** que Datamaq instala para sus clientes, asegurando que la telemetría reporte directamente al **servidor propio Datamaq Telemetry en el VPS**, y cómo restaurar la configuración oficial si fuese necesario.

> [!IMPORTANT]
> **La configuración del broker cambió el 2026-08-18** (TLS obligatorio + autenticación). Las
> instrucciones previas de esta guía (`puerto 1883`, `NO-SECURITY`, usuario vacío) **ya no
> funcionan** y dejan al medidor sin poder conectar nunca. Ver
> [`docs/troubleshooting-conectividad-dispositivos.md`](./troubleshooting-conectividad-dispositivos.md).

---

## 🔒 Configuración obligatoria del broker (fuente de verdad)

Definida en el VPS en `/etc/mosquitto/conf.d/datamaq.conf`:

```
allow_anonymous false
password_file /etc/mosquitto/passwd
listener 1883 127.0.0.1     ← SOLO loopback: inalcanzable desde un medidor
listener 8883 0.0.0.0       ← el único puerto que expone el broker a internet
cafile   /etc/mosquitto/certs/fullchain.pem
certfile /etc/mosquitto/certs/fullchain.pem
keyfile  /etc/mosquitto/certs/privkey.pem
```

Por lo tanto, **todo medidor debe configurarse así y no hay alternativa válida**:

| Parámetro | Valor |
|---|---|
| Broker Host | `mqtt.datamaq.com.ar` |
| Puerto | `8883` |
| Seguridad | `TLS-SERVER-AUTH` |
| Certificado CA | **ISRG Root X1** (Let's Encrypt) — [`isrg_root_x1.pem`](../isrg_root_x1.pem) en la raíz del repo |
| Usuario MQTT | `datamaq_device` |
| Contraseña MQTT | valor de `MQTT_PASSWORD` en `/var/www/datamaq-telemetry/.env` del VPS (**no se versiona**) |
| Client ID | la MAC del equipo, mayúsculas sin separadores (ej. `D48C49F03564`) |
| Keepalive Wi-Fi | `30` s |

El certificado del broker es Let's Encrypt para `CN=mqtt.datamaq.com.ar`; **se renueva cada 90 días**, así que el host configurado en el medidor debe ser el dominio, nunca la IP (con IP falla la validación del nombre).

---

## 🎯 Resumen de Perfiles

Perfiles predefinidos en [`profiles/`](../profiles):

1. **`profiles/datamaq_server.json` (Producción Datamaq):** `mqtt.datamaq.com.ar:8883`,
   `TLS-SERVER-AUTH`, usuario `datamaq_device`, CA resuelta desde `isrg_root_x1.pem`.
   La contraseña queda vacía a propósito y debe inyectarse al aplicar el perfil.
2. **`profiles/powermeter_official.json` (Fábrica Oficial):** `mqtt.powermeter.com.ar:8884`,
   `TLS-SERVER-AUTH` con la CA propia de Powermeter (embebida en el perfil).

---

## 🚀 Método 1: Aprovisionamiento Automatizado (Recomendado)

Conectado a la red Wi-Fi del propio equipo (SSID `Powermeter-<MAC>`, gateway `192.168.4.1`):

### 1. Conectar el medidor al servidor Datamaq

```bash
export MQTT_PASSWORD='<contraseña de datamaq_device>'
python3 scripts/provision_device.py --profile datamaq --reboot
```

El script **valida antes de enviar nada** y aborta si la combinación no puede funcionar
(puerto 1883, TLS sin CA, o credenciales faltantes). También podés sobrescribir puntualmente:
`--broker-host`, `--broker-port`, `--security`, `--mqtt-username`, `--mqtt-password`, `--mqtt-ca-file`.

### 2. Verificar el estado de conexión

```bash
python3 scripts/provision_device.py --status
```

Devuelve el `status.json` del equipo **y un diagnóstico explícito** que distingue las dos causas
posibles de "no reporta": Wi-Fi no asociado vs. Wi-Fi OK pero broker rechazando.

### 3. (Opcional) Restaurar al servidor oficial de Powermeter

```bash
python3 scripts/provision_device.py --profile powermeter-official --reboot
```

---

## 🖥️ Método 2: Configuración Manual desde la Interfaz Web

Desde el navegador en `http://192.168.4.1/home.html`:

1. Credenciales web del equipo: usuario `admin`, contraseña `powermeter`.
2. Sección **MQTT**:
   * **Habilitar MQTT:** `Activado`
   * **Tópicos extendidos:** `Activado`
   * **Broker Host:** `mqtt.datamaq.com.ar`
   * **Puerto:** `8883`
   * **Seguridad:** `TLS-SERVER-AUTH`
   * **Client ID:** la MAC del equipo (ej. `D48C49F03564`)
   * **Usuario:** `datamaq_device`
   * **Contraseña:** la de `MQTT_PASSWORD` del `.env` de producción
3. Sección **Certificado CA MQTT:** pegar el contenido de `isrg_root_x1.pem`.
4. **Guardar MQTT** y luego reiniciar el equipo desde la sección **Reinicio**.

> [!WARNING]
> Guardar el certificado CA vacío **borra** el CA que el equipo tenía y rompe el TLS. Si sólo
> vas a cambiar host/puerto/credenciales, no toques ese campo. (`provision_device.py` ya
> contempla esto y omite el POST del CA cuando no tiene uno para enviar.)

---

## ✅ Verificación desde el servidor

```bash
# Eventos de medidores en el broker, sin el ruido de escáneres de internet
./scripts/logs.sh --mqtt --device

# Un equipo puntual
./scripts/logs.sh --mqtt --device D48C49F03564
```

Una conexión sana se ve así:

```
<epoch>: New connection from <IP pública del cliente> on port 8883.
<epoch>: New client connected from <IP> as D48C49F03564 (p2, c1, k30, u'datamaq_device').
```

---

## 📊 Auto-registro en la Plataforma Datamaq

Cuando el equipo se reinicie y se conecte:

1. Publicará en `m/wifi/{MAC}/add` y `m/wifi/{MAC}/status`.
2. El worker de Datamaq creará el registro en la tabla `devices` de MySQL con su número de serie, modelo y firmware.
3. Las mediciones instantáneas (`/inst`) y de energía (`/acc`) comenzarán a persistirse de inmediato.
