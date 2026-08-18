# Guía de Aprovisionamiento de Medidores Powermeter para Clientes Datamaq

Esta guía explica cómo configurar los medidores de energía **Powermeter** que Datamaq instala para sus clientes, asegurando que la telemetría reporte directamente a tu **servidor propio Datamaq Telemetry en tu VPS** y cómo restaurar la configuración oficial si fuese necesario.

---

## 🎯 Resumen de Perfiles

Se incluyen dos perfiles predefinidos en la carpeta [`profiles/`](file:///home/agustin/proyectos_software/datamaq-telemetry/profiles):

1. **`profiles/datamaq_server.json` (Producción Datamaq):**
   * **Broker Host:** IP pública o dominio de tu VPS (ej. `mqtt.datamaq.com.ar`).
   * **Broker Port:** `1883` (Sin TLS) o `8883` (Con TLS).
   * **Seguridad:** `NO-SECURITY` (o `TLS-SERVER-AUTH`).
   * **Ingesta:** Los datos se registran automáticamente en tu base de datos MySQL y se muestran en tus dashboards / WebSockets.

2. **`profiles/powermeter_official.json` (Fábrica Oficial):**
   * **Broker Host:** `mqtt.powermeter.com.ar`.
   * **Broker Port:** `8884`.
   * **Seguridad:** `TLS-SERVER-AUTH` con el certificado CA oficial de Powermeter.

---

## 🚀 Método 1: Aprovisionamiento Automatizado (Recomendado)

Conectado a la red Wi-Fi del equipo (ej: `Powermeter-D48C49F03564` en `192.168.4.1`):

### 1. Conectar el medidor a tu Servidor Datamaq:
```bash
python3 scripts/provision_device.py --profile datamaq --broker-host 190.x.x.x --broker-port 1883
```
*(Puedes pasar `--broker-host` con la IP o dominio de tu VPS)*

### 2. Verificar el estado de conexión:
```bash
python3 scripts/provision_device.py --status
```

### 3. (Opcional) Restaurar al servidor oficial de Powermeter:
```bash
python3 scripts/provision_device.py --profile powermeter-official
```

---

## 🖥️ Método 2: Configuración Manual desde la Interfaz Web

Si prefieres hacerlo desde el navegador en `http://192.168.4.1/home.html`:

1. Ingresar credenciales Web:
   * **Usuario:** `admin`
   * **Contraseña:** `powermeter`
2. Ir a la sección **MQTT**:
   * **Habilitar MQTT:** `Activado`
   * **Tópicos extendidos:** `Activado`
   * **Broker Host:** `[IP_O_DOMINIO_DE_TU_VPS]`
   * **Puerto:** `1883` (o `8883` si usas TLS)
   * **Seguridad:** `NO-SECURITY` (o `TLS-SERVER-AUTH`)
   * **Client ID:** Mantener la MAC del equipo (`D48C49F03564`)
   * **Usuario / Contraseña:** Vacío (o tus credenciales si configuraste Mosquitto con password)
3. Hacer clic en **Guardar MQTT**.
4. Ir a la sección **Reinicio** y reiniciar el equipo para aplicar los cambios.

---

## 📊 Auto-registro en la Plataforma Datamaq

Cuando el equipo se reinicie y se conecte a Internet:
1. Publicará un mensaje en `m/wifi/{MAC}/add` y `m/wifi/{MAC}/status`.
2. El worker de Datamaq creará automáticamente el registro del dispositivo en la tabla `devices` de MySQL con su número de serie, modelo y firmware.
3. Las mediciones instantáneas (`/inst`) y de energía (`/acc`) comenzarán a persistirse de inmediato.
