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
   ├── REST API (/api/v1/dispositivos, /api/v1/telemetria/...)
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

### 3. Crear la base de datos y aplicar migraciones
Ejecuta el script de inicialización (crea la BD y aplica `alembic upgrade head`):
```bash
venv/bin/python scripts/init_db.py
```

### 4. Migraciones de esquema (Alembic)
El esquema se gestiona con **Alembic** (fuente de verdad: `src/infrastructure/sqlalchemy/models.py`).

- **BD nueva:** `venv/bin/alembic upgrade head` (o `scripts/init_db.py`).
- **BD legacy con drift** (tablas existentes sin `alembic_version`): marcar el baseline y reconciliar:
  ```bash
  venv/bin/alembic stamp 209ce0774d59
  venv/bin/alembic upgrade head
  ```
- **Generar una migración nueva** (diff metadata↔BD contra una BD temporal):
  ```bash
  DATABASE_URL=mysql+pymysql://usuario:pass@127.0.0.1:3306/db_temp venv/bin/alembic revision --autogenerate -m "descripcion"
  ```
- **Revertir la última revisión:** `venv/bin/alembic downgrade -1`

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
| **Planes SaaS** | `GET /api/v1/planes?solo_publicos=true` | Catálogo de planes freemium/privados |
| | `POST /api/v1/planes` | Crear nuevo plan de suscripción |
| **Organizaciones** | `GET /api/v1/organizaciones` | Listar clientes y organizaciones |
| | `POST /api/v1/organizaciones` | Registrar nueva organización |
| **Plantas** | `GET /api/v1/plantas?organizacion_id=...` | Listar sedes/establecimientos |
| | `POST /api/v1/plantas` | Registrar nueva planta |
| **Dispositivos** | `GET /api/v1/dispositivos?planta_id=...` | Listar medidores Powermeter |
| | `POST /api/v1/dispositivos` | Provisionar / registrar medidor |
| | `GET /api/v1/dispositivos/{id}` | Obtener detalle de medidor por UUID o MAC |
| | `PATCH /api/v1/dispositivos/{id}` | Actualizar configuración y metrología (fases_con_ti, tipo_instalacion) |
| **Telemetría** | `GET /api/v1/telemetria/latest/{device_id}` | Última instantánea, acumulado de energía y bloque `analitica` precalculado |
| | `GET /api/v1/telemetria/instantaneous/{device_id}` | Historial de V, I, P, Q, S, FP, VUR y analítica (`limit`, `hours`, `granularity`) |
| | `GET /api/v1/telemetria/energy/{device_id}` | Historial de kWh y kVARh acumulados (`limit`, `hours`) |
| **Alertas** | `GET /api/v1/alertas?device_id=...&solo_abiertas=true` | Consultar alarmas activas / historial |
| | `PATCH /api/v1/alertas/{id}/resolver` | Marcar alerta como resuelta / atendida (`POST` también soportado) |
| **Topología Unifilar & Layout** | `GET /api/v1/planta/unifilar?planta_id=...` | Obtener árbol de nodos unifilares de la planta |
| | `PUT /api/v1/plantas/{planta_id}/unifilar` | Persistir estructura de nodos unifilares |
| | `GET /api/v1/planta/layout?planta_id=...` | Obtener zonas 2D y ubicación porcentual de medidores |
| | `PUT /api/v1/plantas/{planta_id}/layout` | Persistir zonas y coordenadas de layout |
| **Autenticación** | `POST /api/v1/auth/login` | Iniciar sesión (emite cookie `HttpOnly` + token JWT) |
| | `POST /api/v1/auth/guest` | Acceso rápido como invitado (stateless, cookie `HttpOnly`, solo lectura) |
| | `POST /api/v1/auth/logout` | Cerrar sesión (borra la cookie) |
| | `GET /api/v1/auth/me` | Obtener identidad y rol de la sesión actual |
| **Sistema** | `POST /api/v1/system/purge` | Ejecutar purga de telemetría expirada (solo admin) |


---

## ⚡ Ingesta y Optimización de Base de Datos

1. **Live Stream en Tiempo Real:** Los paquetes MQTT entrantes se emiten de inmediato al WebSocket `/ws/live` para visualización sin retardo.
2. **Downsampling a 5 Minutos:** Las mediciones instantáneas se persisten en MySQL con un intervalo configurable (por defecto cada 300 segundos), reduciendo el volumen de disco sin perder resolución de curvas de carga.
3. **Heartbeat Throttling (60s):** El estado `ONLINE` y `last_seen_at` del medidor se actualiza en la base de datos a lo sumo 1 vez por minuto, evitando escrituras redundantes continuas.
4. **Caché en Memoria:** La resolución de dirección MAC a identificador interno utiliza una caché en memoria de alta velocidad.
5. **Purga Segura:** Vía API o CLI por lotes (`python scripts/purge_telemetry.py --days 7 --batch-size 1000`).

---

## 🔒 Seguridad

### Modelo de amenazas

| Amenaza | Mitigación |
|---|---|
| Acceso no autenticado a la API | Autenticación obligatoria por defecto (`AUTH_REQUIRED=true`) vía JWT |
| Fuerza bruta en el login | Rate limiting por usuario (`LOGIN_MAX_INTENTOS`, `LOGIN_VENTANA_SEGUNDOS`) |
| Secreto JWT débil o por defecto | Validación de `API_SECRET_KEY` en producción (mínimo 16 caracteres) |
| Credenciales de BD expuestas | Validación de `DB_PASSWORD` en producción; sin contraseña en flags de CLI |
| MQTT sin cifrado / anónimo | `MQTT_TLS_ENABLED`, `MQTT_TLS_CA_CERTS` y credenciales de broker; listener 8883 TLS en `deploy/mosquitto/mosquitto.conf` con `allow_anonymous false` |
| Payload MQTT malicioso o excesivo | Límite `MQTT_MAX_PAYLOAD_BYTES` y sanitización de campos de entrada |
| Headers de seguridad ausentes | La app emite HSTS (solo producción), CSP, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` y `Referrer-Policy: no-referrer` |
| Fuga de secretos en logs | Procesador `redactar_secretos` y logs sin payload bruto |
| Robo de token vía XSS | Cookie `HttpOnly` (`datamaq_token`) no legible por JavaScript + `SameSite=strict` |
| CORS abierto | `CORS_ORIGINS` vacío por defecto (sin `*`) |

> En desarrollo local se puede desactivar la autenticación con `AUTH_REQUIRED=false` y `DEBUG=true`.

---

## 🧪 Pruebas y Calidad de Código (Gauntlet)

```bash
# Gauntlet completo (integridad, estilo, tipado, cobertura >=85%, integración)
./scripts/ci.sh

# Gauntlet pre-push (etapas 1-4, sin integración)
./scripts/pre-push.sh

# Push y Despliegue con Feedback en Vivo (CI & CD Deploy en VPS)
./push.sh               # o bien: git push-watch
```

Verificación individual:

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
