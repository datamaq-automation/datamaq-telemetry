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

---

## ▶️ Ejecución en Local

### Iniciar la API y el Servicio de Ingesta MQTT:
```bash
./run.sh
```
*(El script activa `venv/`, exporta `PYTHONPATH=.` y ejecuta `uvicorn src.main:app --reload` en `:8000`)*

- **Documentación Swagger interactiva**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Documentación ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Stream WebSockets en vivo**: `ws://localhost:8000/ws/live`
- **Health Check**: `http://localhost:8000/health`

---

## 🔌 Catálogo de Endpoints REST

| Módulo | Método & Ruta | Descripción |
|---|---|---|
| **Planes SaaS** | `GET /api/planes?solo_publicos=true` | Catálogo de planes freemium/privados |
| | `POST /api/planes` | Crear nuevo plan de suscripción |
| **Organizaciones** | `GET /api/organizaciones` | Listar clientes y organizaciones |
| | `POST /api/organizaciones` | Registrar nueva organización |
| **Plantas** | `GET /api/plantas?organizacion_id=...` | Listar sedes/establecimientos |
| | `POST /api/plantas` | Registrar nueva planta |
| **Dispositivos** | `GET /api/dispositivos?planta_id=...` | Listar medidores Powermeter |
| | `POST /api/dispositivos` | Provisionar / registrar medidor |
| | `GET /api/dispositivos/{id}` | Obtener detalle de medidor por UUID o MAC |
| **Telemetría** | `GET /api/telemetria/latest/{id}` | Última instantánea y acumulado de energía |
| | `GET /api/telemetria/instantaneas/{id}` | Historial de V, I, P, Q, S, FP con límite |
| | `GET /api/telemetria/energias/{id}` | Historial de kWh y kVARh acumulados |
| **Alertas** | `GET /api/alertas?device_id=...&solo_abiertas=true` | Consultar alarmas activas / historial |
| | `POST /api/alertas/{id}/resolver` | Marcar alerta como atendida / resuelta |
| **Sistema** | `POST /api/system/purga` | Ejecutar purga de telemetría expirada |

---

## ⚡ Ingesta y Optimización de Base de Datos

1. **Live Stream en Tiempo Real:** Los paquetes MQTT entrantes se emiten de inmediato al WebSocket `/ws/live` para visualización sin retardo.
2. **Downsampling a 5 Minutos:** Las mediciones instantáneas se persisten en MySQL con un intervalo configurable (por defecto cada 300 segundos), reduciendo el volumen de disco sin perder resolución de curvas de carga.
3. **Heartbeat Throttling (60s):** El estado `ONLINE` y `last_seen_at` del medidor se actualiza en la base de datos a lo sumo 1 vez por minuto, evitando escrituras redundantes continuas.
4. **Caché en Memoria:** La resolución de dirección MAC a identificador interno utiliza una caché en memoria de alta velocidad.
5. **Purga Segura:** Vía API o CLI por lotes (`python scripts/purge_telemetry.py --days 7 --batch-size 1000`).

---

## 🧪 Pruebas y Calidad de Código (Gauntlet)

```bash
# Tests unitarios e integración
venv/bin/pytest

# Verificación estricta de arquitectura Clean Architecture & DDD
venv/bin/python scripts/verify_architecture.py

# Linter y Formato
venv/bin/ruff check .
venv/bin/ruff format --check .
```

---

## 📡 Cómo apuntar tu Powermeter a este servidor

Desde la interfaz web de configuración del Powermeter (`http://192.168.4.1`) o mediante el script CLI:
```bash
python scripts/provision_device.py --profile datamaq --broker-host [TU_IP_O_DOMINIO]
```

Para más detalles, consulta la [Guía de Aprovisionamiento](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/provisioning_guide.md) y la [Especificación MQTT](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/powermeter_mqtt_protocol.md).

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
