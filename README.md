# Datamaq Telemetry Platform

Plataforma de backend, ingesta de telemetría en tiempo real y persistencia para la flota de medidores de energía **Powermeter** (SmartPlus, Home, Pro, Solar, Automate).

Construido para despliegues ligeros y directos sin Docker (**Python 3 + venv + MySQL / MariaDB + Mosquitto + FastAPI**).

---

## 🏗 Arquitectura del Sistema

```
[ Powermeter (ESP32) ]
        │ (MQTT: m/wifi/{uid}/inst, acc, status)
        ▼
[ Mosquitto Broker (1883 / 8883) ]
        │
        ▼
[ Ingestion Worker & API (FastAPI) ]
   ├── Ingesta y normalización de telemetría
   ├── WebSockets en vivo (/ws/live)
   ├── REST API (/api/devices, /api/telemetry/...)
   └── Persistencia en MySQL (InnoDB / series temporales)
        │
        ▼
[ Base de Datos MySQL: datamaq_telemetry ]
   ├── organizations & facilities (Multi-tenancy)
   ├── devices (Auto-registro de flota)
   ├── telemetry_instantaneous (V, I, P, Q, S, FP)
   ├── telemetry_energy (kWh, kVARh importado/exportado)
   └── device_alerts & device_status_logs
```

---

## 🚀 Requisitos Previos

1. **Python 3.10+**
2. **MySQL / MariaDB** (servicio activo en el sistema)
3. **Mosquitto MQTT Broker**:
   ```bash
   sudo apt update
   sudo apt install -y mosquitto mosquitto-clients
   sudo systemctl enable mosquitto --now
   ```

---

## 🛠 Instalación y Configuración

### 1. Clonar e inicializar el entorno virtual
```bash
cd ~/proyectos_software/datamaq-telemetry
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configurar variables de entorno
Copia el archivo `.env.example` a `.env` y edita tus credenciales de MySQL y MQTT:
```bash
cp .env.example .env
nano .env
```

### 3. Crear la base de datos y tablas
Ejecuta el script de inicialización:
```bash
venv/bin/python scripts/init_db.py
```
*(Opcionalmente puedes importar directamente `schema.sql` desde tu cliente MySQL/phpMyAdmin)*

---

## ▶️ Ejecución en Local

### Iniciar la API y el Servicio de Ingesta MQTT:
```bash
venv/bin/python main.py
```
- **Documentación Swagger interactiva**: `http://localhost:8000/docs`
- **Stream WebSockets en tiempo real**: `ws://localhost:8000/ws/live`
- **Health Check**: `http://localhost:8000/health`

---

## 📡 Cómo apuntar tu Powermeter a este servidor

Desde la interfaz web de configuración del Powermeter (`http://192.168.4.1`) o mediante POST a `/mqtt_config.json`:

1. **Broker Host**: La IP local de tu máquina en la red Wi-Fi (ej: `192.168.4.2` o la IP de tu red LAN) o la IP pública de tu VPS.
2. **Broker Port**: `1883` (o `8883` con TLS).
3. **Seguridad**: `NO-SECURITY` (en local) o `TLS-SERVER-AUTH` (en VPS con certificado).
4. **Client ID**: Dejar el UID por defecto de la MAC (ej: `D48C49F03564`).

Una vez conectado, el equipo publicará automáticamente a los tópicos y el servidor de Datamaq lo registrará en la base de datos.

---

## 🌐 Despliegue en VPS (Producción con Systemd)

1. Copiar el archivo de servicio a systemd:
   ```bash
   sudo cp systemd/datamaq-api.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable datamaq-api --now
   ```

2. Ver estado y logs:
   ```bash
   sudo systemctl status datamaq-api
   journalctl -u datamaq-api -f
   ```
