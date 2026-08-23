# Especificación de Protocolo MQTT — Medidores Powermeter

Este documento detalla el protocolo de comunicación MQTT implementado por los medidores de energía **Powermeter** (SmartPlus, Home, Pro, Solar, Automate) y cómo la plataforma **Datamaq Telemetry** procesa e ingesta sus datos.

---

## 1. Arquitectura de Conexión

```
┌─────────────────────────┐              ┌─────────────────────────┐
│   Powermeter (ESP32)    │              │   Datamaq Telemetry     │
│                         │              │   (VPS / Servidor)      │
│  Publica:               │   MQTT       │                         │
│  - inst, acc, status    ├─────────────►│   Mosquitto Broker      │
│                         │  QoS: 1      │         │               │
│  Suscribe:              │  Keepalive:  │         ▼               │
│  - conf/com             │  30s         │   Worker Ingesta FastAPI│
│                         │◄─────────────┤   (Paho-MQTT + MySQL)   │
└─────────────────────────┘              └─────────────────────────┘
```

* **Client ID:** Identificador único basado en la dirección MAC del ESP32 en mayúsculas sin separadores (ej: `D48C49F03564`).
* **QoS por defecto:** `1` (At least once).
* **Keepalive:** `30` segundos (vía Wi-Fi) / `60` segundos (vía Móvil/4G).
* **Clean Session:** `true`.

---

## 2. Mapa de Tópicos

El prefijo estándar es `m/wifi/{UID}/`:

| Tópico | Dirección | Descripción | Payload |
|---|---|---|---|
| `m/wifi/{UID}/inst` | Dispositivo ➔ Servidor | Mediciones instantáneas (V, I, P, Q, S, FP) | JSON Fase R, S, T y Total |
| `m/wifi/{UID}/acc` | Dispositivo ➔ Servidor | Energía activa y reactiva acumulada | JSON con kWh y kVARh |
| `m/wifi/{UID}/energyio` | Dispositivo ➔ Servidor | Energía neta, importada y exportada | JSON bidireccional |
| `m/wifi/{UID}/status` | Dispositivo ➔ Servidor | Calidad Wi-Fi, RSSI, IP y uptime | JSON de estado |
| `m/wifi/{UID}/event` | Dispositivo ➔ Servidor | Alarmas de límites superados | JSON de evento |
| `m/wifi/{UID}/add` | Dispositivo ➔ Servidor | Auto-registro en primer encendido | JSON con info del equipo |
| `m/wifi/{UID}/onoff` | Dispositivo ➔ Servidor | Notificación de encendido / apagado | JSON de estado de relé/energía |
| `m/wifi/{UID}/conf/com` | Servidor ➔ Dispositivo | Comandos de configuración remota | JSON de comando |
| `m/wifi/{UID}/conf/rta` | Dispositivo ➔ Servidor | Respuesta a comandos del servidor | JSON de resultado |

---

## 3. Esquemas de Payload JSON

### A. Telemetría Instantánea (`m/wifi/{UID}/inst`)

> [!NOTE]
> **Cadencia de Publicación:**  
> • **Modo Estándar de Fábrica (Firmware SmartPlus / HOME V2.0):** Publicación periódica **cada 5 minutos (300 segundos)** sincronizada al segundo `:00`/`:01` de cada ventana temporal.  
> • **Modo Alta Frecuencia / Ráfaga:** Soporte backend para publicaciones sub-minutales (cada 1 a 5 segundos) en tiempo real.

El backend procesa de forma transparente dos estructuras de payload:

#### 1. Formato Compacto Nativo (Firmware Oficial):
```json
{
  "t": 1787447872,
  "a": 0,
  "f": [
    {"n": "R", "v": 228.7, "i": 12.4, "p": 2835.8, "q": 320.1},
    {"n": "S", "v": 228.3, "i": 10.1, "p": 2305.8, "q": 210.0},
    {"n": "T", "v": 229.1, "i": 8.5, "p": 1947.3, "q": 180.5}
  ]
}
```

#### 2. Formato Extendido / Normalizado:
```json
{
  "timestamp": 1723652400,
  "phase_r": {
    "voltage_V": 228.7,
    "current_A": 12.4,
    "net_active_power_W": 2835.8,
    "net_reactive_power_VAR": 320.1,
    "net_apparent_power_VA": 2853.8,
    "power_factor": 0.99
  },
  "phase_s": {
    "voltage_V": 228.3,
    "current_A": 10.1,
    "net_active_power_W": 2305.8,
    "net_reactive_power_VAR": 210.0,
    "net_apparent_power_VA": 2315.3,
    "power_factor": 0.99
  },
  "phase_t": {
    "voltage_V": 229.1,
    "current_A": 8.5,
    "net_active_power_W": 1947.3,
    "net_reactive_power_VAR": 180.5,
    "net_apparent_power_VA": 1955.6,
    "power_factor": 0.99
  },
  "total": {
    "net_active_power_W": 7088.9,
    "net_reactive_power_VAR": 710.6,
    "net_apparent_power_VA": 7124.7,
    "power_factor": 0.99
  }
}
```


### B. Energía Acumulada (`m/wifi/{UID}/acc` / `energyio`)

```json
{
  "timestamp": 1723652400,
  "total": {
    "net_active_energy_KWH": 12450.85,
    "net_reactive_energy_KVARH": 3120.40,
    "imported_active_energy_KWH": 12450.85,
    "exported_active_energy_KWH": 0.00,
    "imported_reactive_energy_KVARH": 3120.40,
    "exported_reactive_energy_KVARH": 0.00
  }
}
```

### C. Estado y Diagnóstico (`m/wifi/{UID}/status`)

```json
{
  "wifi_sta": {
    "enabled": true,
    "connected": true,
    "quality": 85,
    "dbm": -58,
    "ssid": "Planta_Industrial_1",
    "ip": "192.168.1.150",
    "mac": "D4:8C:49:F0:35:64"
  },
  "device_info": {
    "serial_number": "377",
    "device_name": "Tablero Principal Molino",
    "device_model": "SmartPlus",
    "device_fw": "V1.3.0",
    "hw_model": "HOME V2.0",
    "uptime": 128540
  }
}
```

---

## 4. Perfiles de Configuración del Broker

El equipo dispone de dos perfiles según el entorno:

1. **Perfil Oficial Powermeter:** Apunta a `mqtt.powermeter.com.ar:8884` con TLS y certificado CA oficial.
2. **Perfil Datamaq Telemetry:** Apunta a tu servidor VPS (`broker_host`, puerto `1883` o `8883`) gestionado por tu plataforma.

---

## 5. Política de Ingesta, Downsampling y Persistencia

Para optimizar el uso de la base de datos MySQL manteniendo alta fidelidad visual en los tableros de control:

1. **Live Stream WebSocket (Tiempo Real):**
   * Cada mensaje MQTT recibido en `m/wifi/{UID}/...` se retransmite de inmediato a los clientes conectados a `ws://localhost:8000/ws/live`.
   * Cero latencia para visualización en vivo de tensión, corriente y potencia.

2. **Downsampling a 5 Minutos (Base de Datos):**
   * Las mediciones instantáneas (`/inst`) se persisten en la tabla `telemetry_instantaneous` cada 300 segundos por dispositivo.
   * Si se detectan anomalías de calidad de energía (ej: tensión fuera de rango $\pm 10\%$), las alertas se persisten de inmediato independientemente del downsampling.

3. **Throttling de Latidos (60s):**
   * La fecha `last_seen_at` y el estado `ONLINE` del medidor en la tabla `devices` se actualizan en la base de datos a lo sumo 1 vez por minuto.

4. **Acumulados de Energía (`/acc` / `/energyio`):**
   * Se registran en la tabla `telemetry_energy` con valores acumulados monótonos crecientes de kWh y kVARh para cálculos de consumo y facturación.
