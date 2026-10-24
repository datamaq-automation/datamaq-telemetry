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
   ├── Jerarquía SGE / ISA-95 (Configuración declarativa GitOps en ./data/)
   │    ├── Nivel 4 (Empresa): Organizaciones y planes comerciales
   │    ├── Nivel 3 (Sitio): Plantas y metas de eficiencia ISO 50001
   │    └── Nivel 2 (Área/Proceso): Unifilar eléctrico, USEs y Layouts 2D
   └── Persistencia en MySQL (InnoDB / series temporales y estados)
        │
        ▼
[ Base de Datos MySQL: datamaq_telemetry ]
   ├── users & dispositivos_confiables (Autenticación y RBAC)
   ├── devices & machines (Auto-registro de flota y disponibilidad OEE)
   ├── telemetry_instantaneous (V, I, P, Q, S, FP)
   ├── telemetry_energy (kWh, kVARh importado/exportado)
   └── device_alerts & device_status_logs
```

> 📘 Para detalles profundos sobre el modelo industrial de activos, consultar [`docs/arquitectura-sge-isa95.md`](docs/arquitectura-sge-isa95.md).

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
cd ~/proyectos_software/datamaq/datamaq-telemetry
uv venv --python 3.12 .venv
uv pip sync --python .venv/bin/python requirements.lock   # versiones exactas, las mismas que CI y producción
```

`scripts/pre-push.sh` (el hook de pre-push) exige que `.venv/` exista y sea Python 3.12, y avisa si
lo instalado no coincide con `requirements.lock`.

Python 3.12 es la versión de producción y de CI. `requirements.txt` declara los rangos aceptados;
`requirements.lock` fija las versiones exactas que se instalan. Si cambiás `requirements.txt`,
regenerá el lock y commiteá los dos (CI falla si solo cambia el `.txt`):

```bash
uvx --python 3.12 --from pip-tools pip-compile -o requirements.lock requirements.txt
```

Después de cualquier cambio del lock (propio o traído con `git pull`), re-sincronizar el entorno:
`uv pip sync --python .venv/bin/python requirements.lock`.

### 1.1. Clonar los datos maestros (repo independiente)
`data/` (organizaciones, facturas de distribuidora) vive en un repositorio git
separado, no submódulo, para desacoplar su historial del de código:
```bash
git clone git@github.com:datamaq-automation/datamaq-data.git data
```
Requiere acceso al repo `datamaq-automation/datamaq-data` (privado).

### 2. Configurar variables de entorno
Copia el archivo `.env.example` a `.env` y edita tus credenciales de MySQL y MQTT:
```bash
cp .env.example .env
nano .env
```

### 3. Crear la base de datos y aplicar migraciones
Ejecuta el script de inicialización (crea la BD y aplica `alembic upgrade head`):
```bash
.venv/bin/python scripts/init_db.py
```

### 4. Migraciones de esquema (Alembic)
El esquema se gestiona con **Alembic** (fuente de verdad: `src/infrastructure/sqlalchemy/models.py`).

- **BD nueva:** `.venv/bin/alembic upgrade head` (o `scripts/init_db.py`).
- **BD legacy con drift** (tablas existentes sin `alembic_version`): marcar el baseline y reconciliar:
  ```bash
  .venv/bin/alembic stamp 209ce0774d59
  .venv/bin/alembic upgrade head
  ```
- **Generar una migración nueva** (diff metadata↔BD contra una BD temporal):
  ```bash
  DATABASE_URL=mysql+pymysql://usuario:pass@127.0.0.1:3306/db_temp .venv/bin/alembic revision --autogenerate -m "descripcion"
  ```
- **Revertir la última revisión:** `.venv/bin/alembic downgrade -1`

---

---

## ▶️ Ejecución en Local

### Iniciar la API y el Servicio de Ingesta MQTT:
```bash
./run.sh
```
*(El script activa `.venv/`, exporta `PYTHONPATH=.` y ejecuta `uvicorn src.main:app --reload` en `:8000`)*

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
| | `GET /api/v1/telemetria/instantaneous/{device_id}` | Historial de V, I, P, Q, S, FP, VUR y analítica (`limit`, `hours`, `granularity`, `hasta`); headers `X-Datos-Desde` y `X-Potencia-Referencia-W` |
| | `GET /api/v1/telemetria/energy/{device_id}` | Historial de kWh y kVARh (`limit`, `days`, `granularity`, `timezone`); header `X-Datos-Desde` |
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
| **Desagregación de Cargas** | `GET`/`POST` `/api/v1/cargas` | Catálogo de cargas detrás de un medidor agregado |
| | `PUT /api/v1/cargas/{id}/firma` | Fijar firma eléctrica a mano (calibración sin campaña) |
| | `GET /api/v1/cargas/perfil?device_id=...&dias=14` | Línea base, ciclado y regímenes — funciona sin ninguna firma calibrada |
| | `POST /api/v1/cargas/campanas/activas` \| `/pasivas` | Abrir campaña de caracterización (ráfaga acotada, no altera la cadencia permanente) |
| | `PATCH /api/v1/cargas/campanas/{id}/finalizar` | Cerrar campaña y calcular la firma medida |
| | `POST /api/v1/cargas/analisis?device_id=...` | Disparar el batch de detección y atribución (idempotente) |
| | `GET /api/v1/cargas/atribucion?device_id=...` | kWh por carga del período, con el residual `NO_ATRIBUIDO` explícito |
| | `PATCH /api/v1/cargas/intervalos/{id}/corregir` | Corrección humana; construye el dataset etiquetado |
| **Sistema** | `POST /api/v1/system/purge` | Ejecutar purga de telemetría expirada (solo admin) |


---

## ⚡ Ingesta y Optimización de Base de Datos

1. **Live Stream en Tiempo Real:** Los paquetes MQTT entrantes se emiten de inmediato al WebSocket `/ws/live` para visualización sin retardo.
2. **Downsampling a 5 Minutos:** Las mediciones instantáneas se persisten en MySQL con un intervalo configurable (por defecto cada 300 segundos), reduciendo el volumen de disco sin perder resolución de curvas de carga.
3. **Heartbeat Throttling (60s):** El estado `ONLINE` y `last_seen_at` del medidor se actualiza en la base de datos a lo sumo 1 vez por minuto, evitando escrituras redundantes continuas.
4. **Caché en Memoria:** La resolución de dirección MAC a identificador interno utiliza una caché en memoria de alta velocidad.
5. **Purga Segura:** Vía API o CLI por lotes (`python scripts/purge_telemetry.py --days 7 --batch-size 1000`).
6. **Campañas de Caracterización:** Durante una ventana declarada, las lecturas se guardan además a caudal completo (1-5 s) en `campaign_samples`, un sumidero paralelo que **no altera el downsampling ni la serie permanente**. Es la única forma de medir la firma de una carga cuyo encendido dura menos que el intervalo de muestreo. Ver [`docs/desagregacion-cargas-nilm.md`](file:///home/agustin/proyectos_software/datamaq-telemetry/docs/desagregacion-cargas-nilm.md).

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

Antes de correr los tests, la configuración debe permitir arrancar la app. Si copiás `.env.example` tal cual, `APP_ENV=production` exige una `API_SECRET_KEY` fuerte, y los tests fallan sin ella. Para desarrollo local, definí estas variables (o ponelas en `.env`):

```bash
export APP_ENV=development
export API_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
```

Los tests que leen la configuración de organizaciones (`data/`, por ejemplo unifilar, YAML de organizaciones y SGE) necesitan el repositorio `datamaq-data` clonado en `./data`. Sin él, fallan por falta de datos, no por código.

Verificación individual:

```bash
# Tests unitarios e integración
.venv/bin/pytest

# Verificación estricta de arquitectura Clean Architecture & DDD
.venv/bin/python scripts/verify_architecture.py

# Linter y Formato
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

### Post-Deploy Validation (Smoke Test)

Después de cada despliegue, se ejecutan smoke tests automáticamente en CI para validar:
- ✓ Conectividad a BD (status 200/503)
- ✓ Migraciones sincronizadas
- ✓ Datos maestros (datamaq-data) cargados
- ✓ No hay logs CRITICAL en startup

```bash
# Ejecutar manualmente (local o post-deploy)
.venv/bin/pytest tests/e2e/test_smoke_post_deploy.py -v

# En CI/CD (deploy.yml)
pytest tests/e2e/test_smoke_post_deploy.py -v
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
