# Diagrama Entidad-Relación (ERD) — Datamaq Telemetry

> [!NOTE]
> Este documento se genera de forma 100% automática a partir de los modelos de SQLAlchemy
> (`src/infrastructure/sqlalchemy/models.py`) mediante el script `scripts/generate_erd.py`.

## 1. Diagrama de Relaciones

```mermaid
erDiagram
    CHARACTERIZATION_CAMPAIGNS ||--o{ CAMPAIGN_SAMPLES : "FK_campaign_id"
    DEVICES ||--o{ AUDITORIA_CAMBIOS_TI : "FK_device_id"
    DEVICES ||--o{ CHARACTERIZATION_CAMPAIGNS : "FK_device_id"
    DEVICES ||--o{ DEVICE_ALERTS : "FK_device_id"
    DEVICES ||--o{ DEVICE_STATUS_LOGS : "FK_device_id"
    DEVICES ||--o{ DISPOSITIVO_DIAGNOSTICOS : "FK_device_id"
    DEVICES ||--o{ LOADS : "FK_device_id"
    DEVICES ||--o{ LOAD_ACTIVITY_INTERVALS : "FK_device_id"
    DEVICES ||--o{ MACHINES : "FK_device_id"
    DEVICES ||--o{ TELEMETRIA_ANOMALIAS : "FK_device_id"
    DEVICES ||--o{ TELEMETRY_ENERGY : "FK_device_id"
    DEVICES ||--o{ TELEMETRY_INSTANTANEOUS : "FK_device_id"
    FACILITIES ||--o{ DEVICES : "FK_facility_id"
    LOADS ||--o{ CHARACTERIZATION_CAMPAIGNS : "FK_load_id"
    LOADS ||--o{ LOAD_ACTIVITY_INTERVALS : "FK_load_id"
    MACHINES ||--o{ MACHINE_AVAILABILITY_EVENTS : "FK_machine_id"
    MACHINES ||--o{ SCHEDULED_STOPS : "FK_machine_id"
    ORGANIZATIONS ||--o{ FACILITIES : "FK_organization_id"
    ORGANIZATIONS ||--o{ USERS : "FK_organization_id"
    PLANS ||--o{ ORGANIZATIONS : "FK_plan_id"
    USERS ||--o{ AUDITORIA_CAMBIO_CONTRASENA : "FK_usuario_id"
    USERS ||--o{ CAMBIO_CONTRASENA_VALIDACIONES : "FK_usuario_id"
    USERS ||--o{ DISPOSITIVOS_CONFIABLES : "FK_usuario_id"
    USERS ||--o{ OAUTH_CODES : "FK_user_id"
    USERS ||--o{ OAUTH_REFRESH_TOKENS : "FK_user_id"
    USERS ||--o{ USER_FACILITY_ACCESS : "FK_user_id"

    AUDIT_LOGS {
        string id PK
        datetime registrado_en
        string actor_usuario_id
        string actor_email
        string actor_ip
        string actor_user_agent
        string categoria
        string accion
        string resultado
        string recurso_tipo
        string recurso_id
        json metadatos
    }

    AUDITORIA_CAMBIO_CONTRASENA {
        int id PK
        string usuario_id FK
        string ip
        string user_agent
        string estado
        datetime creado_en
    }

    AUDITORIA_CAMBIOS_TI {
        int id PK
        string device_id FK
        string tipo_cambio
        string valor_anterior
        string valor_nuevo
        string motivo
        string commit_git
        string usuario
        datetime timestamp
    }

    CAMBIO_CONTRASENA_VALIDACIONES {
        int id PK
        string usuario_id FK
        string codigo_hash
        int intentos_fallidos
        datetime ttl_expira
        datetime creado_en
        datetime consumido_en
    }

    CAMPAIGN_SAMPLES {
        bigint id PK
        string campaign_id FK
        datetime recorded_at
        decimal active_power_w
        decimal reactive_power_var
        decimal apparent_power_va
        decimal power_factor
        decimal voltage_v
        decimal current_a
    }

    CHARACTERIZATION_CAMPAIGNS {
        string id PK
        string device_id FK
        string load_id FK
        string campaign_type
        string state
        datetime start_at
        datetime planned_end_at
        datetime end_at
        decimal baseline_w
        decimal baseline_var
        int sample_count
        string discard_reason
        string notes
        string created_by_user_id
        datetime created_at
    }

    DEVICE_ALERTS {
        bigint id PK
        string device_id FK
        string alert_type
        string severity
        string message
        boolean is_resolved
        datetime triggered_at
        datetime resolved_at
        string phase
        decimal measured_value
        decimal threshold_value
        string unit
        string category
        string notes
    }

    DEVICE_STATUS_LOGS {
        bigint id PK
        string device_id FK
        datetime recorded_at
        int wifi_rssi_dbm
        int wifi_calidad
        string ip_address
        bigint uptime_seconds
        json raw_payload
        datetime created_at
    }

    DEVICES {
        string id PK
        string facility_id FK
        string device_uid UK
        string serial_number
        string name
        string model
        string hw_version
        string fw_version
        string tag_location
        boolean is_active
        string status
        datetime last_seen_at
        string installation_type
        string phases_with_ct
        string ct_inverted_phases
        string ct_phase_angle_offsets
        string categoria_tarifaria
        boolean penalizacion_reactiva_aplica
        datetime created_at
        datetime updated_at
    }

    DISPOSITIVO_DIAGNOSTICOS {
        bigint id PK
        string device_id FK
        datetime ejecutado_en
        string config_actual
        boolean config_actual_invertido
        string top_candidato
        boolean top_candidato_invertido
        float top_score
        int registros_analizados
        boolean mismatch
        boolean alerta_enviada
        datetime creado_en
    }

    DISPOSITIVOS_CONFIABLES {
        string id PK
        string usuario_id FK
        string token_hash
        string nombre_dispositivo
        string user_agent
        string ip_origen
        datetime creado_en
        datetime ultimo_acceso_en
        datetime expira_en
        boolean revocado
    }

    FACILITIES {
        string id PK
        string organization_id FK
        string name
        string address
        decimal latitude
        decimal longitude
        string layout_svg_url
        datetime created_at
        datetime updated_at
    }

    LOAD_ACTIVITY_INTERVALS {
        bigint id PK
        string device_id FK
        string load_id FK
        datetime start_at
        datetime end_at
        decimal avg_power_w
        decimal delta_reactive_var
        decimal energy_kwh
        decimal confidence
        string origin
        string corrected_by_user_id
        datetime corrected_at
        string notes
        datetime created_at
    }

    LOADS {
        string id PK
        string device_id FK
        string name
        string category
        string electrical_nature
        string operation_pattern
        decimal nameplate_power_w
        decimal signature_power_w
        decimal signature_dispersion_w
        decimal signature_reactive_var
        decimal signature_power_factor
        decimal signature_on_seconds
        decimal signature_on_mad_seconds
        decimal signature_off_seconds
        decimal signature_startup_peak_w
        string signature_source
        int signature_samples
        datetime signature_measured_at
        boolean is_active
        string notes
        datetime created_at
        datetime updated_at
    }

    MACHINE_AVAILABILITY_EVENTS {
        bigint id PK
        string machine_id FK
        string state
        string stop_type
        datetime start_at
        datetime end_at
        decimal avg_power_w
        string origin
        string corrected_by_user_id
        datetime corrected_at
        string notes
    }

    MACHINES {
        string id PK
        string device_id FK
        string name
        decimal on_threshold_w
        int persistence_readings
        decimal persistence_seconds
        datetime created_at
        datetime updated_at
    }

    OAUTH_CLIENTS {
        int id PK
        string client_id UK
        string client_name
        string redirect_uris
        boolean is_trusted
        datetime created_at
    }

    OAUTH_CODES {
        int id PK
        string code_hash UK
        string client_id
        string user_id FK
        string organization_id
        string redirect_uri
        string code_challenge
        string code_challenge_method
        string scope
        datetime expires_at
        boolean used
        datetime created_at
    }

    OAUTH_REFRESH_TOKENS {
        int id PK
        string token_hash UK
        string client_id
        string user_id FK
        string organization_id
        string scope
        datetime expires_at
        datetime revoked_at
        datetime created_at
    }

    ORGANIZATIONS {
        string id PK
        string plan_id FK
        datetime pro_expires_at
        string free_tier_mode
        boolean es_cooperativa
        datetime created_at
        datetime updated_at
    }

    PLANS {
        string id PK
        string name
        string description
        decimal monthly_price_ars
        string visibility
        int retention_days
        int granularity_minutes
        int max_devices
        json notification_channels
        datetime created_at
        datetime updated_at
    }

    SCHEDULED_STOPS {
        string id PK
        string machine_id FK
        datetime start_at
        datetime end_at
        string reason
        string created_by_user_id
        datetime created_at
    }

    TELEMETRIA_ANOMALIAS {
        bigint id PK
        string device_id FK
        datetime recorded_at
        float error_s
        string flag_tipo
        int contador_consecutivos
        string estado
        datetime creado_en
        datetime actualizado_en
    }

    TELEMETRY_ENERGY {
        bigint id PK
        string device_id FK
        datetime recorded_at
        decimal net_active_energy_kwh
        decimal net_reactive_energy_kvarh
        decimal imported_active_energy_kwh
        decimal exported_active_energy_kwh
        decimal imported_reactive_energy_kvarh
        decimal exported_reactive_energy_kvarh
        string source
        datetime created_at
    }

    TELEMETRY_INSTANTANEOUS {
        bigint id PK
        string device_id FK
        datetime recorded_at
        decimal voltage_r
        decimal current_r
        decimal active_power_r
        decimal reactive_power_r
        decimal apparent_power_r
        decimal power_factor_r
        decimal voltage_s
        decimal current_s
        decimal active_power_s
        decimal reactive_power_s
        decimal apparent_power_s
        decimal power_factor_s
        decimal voltage_t
        decimal current_t
        decimal active_power_t
        decimal reactive_power_t
        decimal apparent_power_t
        decimal power_factor_t
        decimal total_active_power
        decimal total_reactive_power
        decimal total_apparent_power
        decimal total_power_factor
        decimal desbalance_tension_porcentaje
        decimal current_n
        decimal voltage_linea_V
        decimal tension_neutro_estimada
        decimal thd_v_r
        decimal thd_i_r
        decimal thd_v_s
        decimal thd_i_s
        decimal thd_v_t
        decimal thd_i_t
        decimal thd_v_promedio_porcentaje
        decimal thd_i_total_porcentaje
        boolean es_dato_confiable
        datetime created_at
    }

    USER_FACILITY_ACCESS {
        string user_id PK
        string facility_id PK
        boolean can_switch
        datetime created_at
    }

    USERS {
        string id PK
        string username UK
        string password_hash
        string role
        boolean is_active
        string totp_secret
        boolean totp_enabled
        json totp_backup_codes
        datetime sesiones_revocadas_antes_de
        string organization_id FK
        datetime created_at
        datetime updated_at
    }

    WEBHOOK_EVENTS {
        string id PK
        string provider
        string event_id
        datetime processed_at
    }

```

## 2. Detalle de Tablas e Índices

### Tabla `audit_logs`

| Columna | Tipo SQL | Clave / Restricción | Nullable |
| :--- | :--- | :--- | :--- |
| `id` | `VARCHAR(36)` | **PRIMARY KEY** | No |
| `registrado_en` | `DATETIME` | - | No |
| `actor_usuario_id` | `VARCHAR(36)` | - | Sí |
| `actor_email` | `VARCHAR(255)` | - | Sí |
| `actor_ip` | `VARCHAR(45)` | - | Sí |
| `actor_user_agent` | `VARCHAR(255)` | - | Sí |
| `categoria` | `VARCHAR(50)` | - | No |
| `accion` | `VARCHAR(100)` | - | No |
| `resultado` | `VARCHAR(20)` | - | No |
| `recurso_tipo` | `VARCHAR(50)` | - | Sí |
| `recurso_id` | `VARCHAR(100)` | - | Sí |
| `metadatos` | `JSON` | - | Sí |

**Índices:**
- `idx_audit_actor_fecha`: (`actor_usuario_id`, `registrado_en`)
- `idx_audit_recurso`: (`recurso_tipo`, `recurso_id`)
- `ix_audit_logs_accion`: (`accion`)
- `ix_audit_logs_actor_usuario_id`: (`actor_usuario_id`)
- `ix_audit_logs_categoria`: (`categoria`)
- `ix_audit_logs_recurso_id`: (`recurso_id`)

### Tabla `auditoria_cambio_contrasena`

| Columna | Tipo SQL | Clave / Restricción | Nullable |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | **PRIMARY KEY** | No |
| `usuario_id` | `VARCHAR(36)` | FK -> `users.id` | No |
| `ip` | `VARCHAR(45)` | - | Sí |
| `user_agent` | `VARCHAR(255)` | - | Sí |
| `estado` | `VARCHAR(50)` | - | No |
| `creado_en` | `DATETIME` | - | No |

**Índices:**
- `idx_auditoria_cambio_contrasena_usuario_creado`: (`usuario_id`, `creado_en`)

### Tabla `auditoria_cambios_ti`

| Columna | Tipo SQL | Clave / Restricción | Nullable |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | **PRIMARY KEY** | No |
| `device_id` | `VARCHAR(36)` | FK -> `devices.id` | No |
| `tipo_cambio` | `VARCHAR(100)` | - | No |
| `valor_anterior` | `TEXT` | - | Sí |
| `valor_nuevo` | `TEXT` | - | Sí |
| `motivo` | `TEXT` | - | Sí |
| `commit_git` | `VARCHAR(40)` | - | Sí |
| `usuario` | `VARCHAR(100)` | - | Sí |
| `timestamp` | `DATETIME` | - | No |

**Índices:**
- `idx_dispositivo_timestamp`: (`device_id`, `timestamp`)
- `idx_tipo_cambio`: (`tipo_cambio`)

### Tabla `cambio_contrasena_validaciones`

| Columna | Tipo SQL | Clave / Restricción | Nullable |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | **PRIMARY KEY** | No |
| `usuario_id` | `VARCHAR(36)` | FK -> `users.id` | No |
| `codigo_hash` | `VARCHAR(64)` | - | No |
| `intentos_fallidos` | `INTEGER` | - | No |
| `ttl_expira` | `DATETIME` | - | No |
| `creado_en` | `DATETIME` | - | No |
| `consumido_en` | `DATETIME` | - | Sí |

**Índices:**
- `idx_cambio_contrasena_validaciones_usuario_creado`: (`usuario_id`, `creado_en`)

### Tabla `campaign_samples`

| Columna | Tipo SQL | Clave / Restricción | Nullable |
| :--- | :--- | :--- | :--- |
| `id` | `BIGINT` | **PRIMARY KEY** | No |
| `campaign_id` | `VARCHAR(36)` | FK -> `characterization_campaigns.id` | No |
| `recorded_at` | `DATETIME` | - | No |
| `active_power_w` | `NUMERIC(12, 2)` | - | Sí |
| `reactive_power_var` | `NUMERIC(12, 2)` | - | Sí |
| `apparent_power_va` | `NUMERIC(12, 2)` | - | Sí |
| `power_factor` | `NUMERIC(4, 3)` | - | Sí |
| `voltage_v` | `NUMERIC(6, 2)` | - | Sí |
| `current_a` | `NUMERIC(8, 2)` | - | Sí |

### Tabla `characterization_campaigns`

| Columna | Tipo SQL | Clave / Restricción | Nullable |
| :--- | :--- | :--- | :--- |
| `id` | `VARCHAR(36)` | **PRIMARY KEY** | No |
| `device_id` | `VARCHAR(36)` | FK -> `devices.id` | No |
| `load_id` | `VARCHAR(36)` | FK -> `loads.id` | Sí |
| `campaign_type` | `VARCHAR(20)` | - | No |
| `state` | `VARCHAR(20)` | - | No |
| `start_at` | `DATETIME` | - | No |
| `planned_end_at` | `DATETIME` | - | No |
| `end_at` | `DATETIME` | - | Sí |
| `baseline_w` | `NUMERIC(10, 2)` | - | Sí |
| `baseline_var` | `NUMERIC(10, 2)` | - | Sí |
| `sample_count` | `INTEGER` | - | No |
| `discard_reason` | `VARCHAR(30)` | - | Sí |
| `notes` | `TEXT` | - | Sí |
| `created_by_user_id` | `VARCHAR(36)` | - | Sí |
| `created_at` | `DATETIME` | - | No |

**Índices:**
- `idx_campaigns_device_state`: (`device_id`, `state`)

### Tabla `device_alerts`

| Columna | Tipo SQL | Clave / Restricción | Nullable |
| :--- | :--- | :--- | :--- |
| `id` | `BIGINT` | **PRIMARY KEY** | No |
| `device_id` | `VARCHAR(36)` | FK -> `devices.id` | No |
| `alert_type` | `VARCHAR(50)` | - | No |
| `severity` | `VARCHAR(8)` | - | No |
| `message` | `TEXT` | - | No |
| `is_resolved` | `BOOLEAN` | - | No |
| `triggered_at` | `DATETIME` | - | No |
| `resolved_at` | `DATETIME` | - | Sí |
| `phase` | `VARCHAR(10)` | - | Sí |
| `measured_value` | `NUMERIC(10, 2)` | - | Sí |
| `threshold_value` | `NUMERIC(10, 2)` | - | Sí |
| `unit` | `VARCHAR(20)` | - | Sí |
| `category` | `VARCHAR(50)` | - | Sí |
| `notes` | `TEXT` | - | Sí |

**Índices:**
- `idx_alerts_dev_resolved`: (`device_id`, `is_resolved`)
- `idx_alerts_resolved_purge`: (`is_resolved`, `resolved_at`)
- `ix_device_alerts_device_id`: (`device_id`)

### Tabla `device_status_logs`

| Columna | Tipo SQL | Clave / Restricción | Nullable |
| :--- | :--- | :--- | :--- |
| `id` | `BIGINT` | **PRIMARY KEY** | No |
| `device_id` | `VARCHAR(36)` | FK -> `devices.id` | No |
| `recorded_at` | `DATETIME` | - | No |
| `wifi_rssi_dbm` | `INTEGER` | - | Sí |
| `wifi_calidad` | `INTEGER` | - | Sí |
| `ip_address` | `VARCHAR(45)` | - | Sí |
| `uptime_seconds` | `BIGINT` | - | Sí |
| `raw_payload` | `JSON` | - | Sí |
| `created_at` | `DATETIME` | - | No |

**Índices:**
- `idx_device_status_dev_time`: (`device_id`, `recorded_at`)
- `idx_device_status_time`: (`recorded_at`)

### Tabla `devices`

| Columna | Tipo SQL | Clave / Restricción | Nullable |
| :--- | :--- | :--- | :--- |
| `id` | `VARCHAR(36)` | **PRIMARY KEY** | No |
| `facility_id` | `VARCHAR(36)` | FK -> `facilities.id` | Sí |
| `device_uid` | `VARCHAR(64)` | UNIQUE | No |
| `serial_number` | `VARCHAR(64)` | - | Sí |
| `name` | `VARCHAR(100)` | - | No |
| `model` | `VARCHAR(50)` | - | No |
| `hw_version` | `VARCHAR(50)` | - | Sí |
| `fw_version` | `VARCHAR(50)` | - | Sí |
| `tag_location` | `VARCHAR(100)` | - | Sí |
| `is_active` | `BOOLEAN` | - | No |
| `status` | `VARCHAR(20)` | - | No |
| `last_seen_at` | `DATETIME` | - | Sí |
| `installation_type` | `VARCHAR(30)` | - | No |
| `phases_with_ct` | `VARCHAR(20)` | - | No |
| `ct_inverted_phases` | `VARCHAR(20)` | - | No |
| `ct_phase_angle_offsets` | `VARCHAR(50)` | - | No |
| `categoria_tarifaria` | `VARCHAR(10)` | - | No |
| `penalizacion_reactiva_aplica` | `BOOLEAN` | - | No |
| `created_at` | `DATETIME` | - | No |
| `updated_at` | `DATETIME` | - | No |

**Índices:**
- `ix_devices_device_uid` (UNIQUE): (`device_uid`)

### Tabla `dispositivo_diagnosticos`

| Columna | Tipo SQL | Clave / Restricción | Nullable |
| :--- | :--- | :--- | :--- |
| `id` | `BIGINT` | **PRIMARY KEY** | No |
| `device_id` | `VARCHAR(36)` | FK -> `devices.id` | No |
| `ejecutado_en` | `DATETIME` | - | No |
| `config_actual` | `VARCHAR(50)` | - | Sí |
| `config_actual_invertido` | `BOOLEAN` | - | Sí |
| `top_candidato` | `VARCHAR(50)` | - | Sí |
| `top_candidato_invertido` | `BOOLEAN` | - | Sí |
| `top_score` | `FLOAT` | - | Sí |
| `registros_analizados` | `INTEGER` | - | Sí |
| `mismatch` | `BOOLEAN` | - | Sí |
| `alerta_enviada` | `BOOLEAN` | - | No |
| `creado_en` | `DATETIME` | - | No |

**Índices:**
- `idx_diagnosticos_device_ejecutado`: (`device_id`, `ejecutado_en`)

### Tabla `dispositivos_confiables`

| Columna | Tipo SQL | Clave / Restricción | Nullable |
| :--- | :--- | :--- | :--- |
| `id` | `VARCHAR(36)` | **PRIMARY KEY** | No |
| `usuario_id` | `VARCHAR(36)` | FK -> `users.id` | No |
| `token_hash` | `VARCHAR(64)` | - | No |
| `nombre_dispositivo` | `VARCHAR(150)` | - | Sí |
| `user_agent` | `VARCHAR(255)` | - | No |
| `ip_origen` | `VARCHAR(45)` | - | No |
| `creado_en` | `DATETIME` | - | No |
| `ultimo_acceso_en` | `DATETIME` | - | No |
| `expira_en` | `DATETIME` | - | No |
| `revocado` | `BOOLEAN` | - | No |

**Índices:**
- `idx_dispositivos_confiables_hash` (UNIQUE): (`token_hash`)
- `idx_dispositivos_confiables_usuario`: (`usuario_id`)

### Tabla `facilities`

| Columna | Tipo SQL | Clave / Restricción | Nullable |
| :--- | :--- | :--- | :--- |
| `id` | `VARCHAR(36)` | **PRIMARY KEY** | No |
| `organization_id` | `VARCHAR(36)` | FK -> `organizations.id` | No |
| `name` | `VARCHAR(150)` | - | No |
| `address` | `VARCHAR(255)` | - | Sí |
| `latitude` | `NUMERIC(10, 8)` | - | Sí |
| `longitude` | `NUMERIC(11, 8)` | - | Sí |
| `layout_svg_url` | `VARCHAR(500)` | - | Sí |
| `created_at` | `DATETIME` | - | No |
| `updated_at` | `DATETIME` | - | No |

### Tabla `load_activity_intervals`

| Columna | Tipo SQL | Clave / Restricción | Nullable |
| :--- | :--- | :--- | :--- |
| `id` | `BIGINT` | **PRIMARY KEY** | No |
| `device_id` | `VARCHAR(36)` | FK -> `devices.id` | No |
| `load_id` | `VARCHAR(36)` | FK -> `loads.id` | Sí |
| `start_at` | `DATETIME` | - | No |
| `end_at` | `DATETIME` | - | No |
| `avg_power_w` | `NUMERIC(12, 2)` | - | Sí |
| `delta_reactive_var` | `NUMERIC(12, 2)` | - | Sí |
| `energy_kwh` | `NUMERIC(12, 4)` | - | Sí |
| `confidence` | `NUMERIC(4, 3)` | - | Sí |
| `origin` | `VARCHAR(20)` | - | No |
| `corrected_by_user_id` | `VARCHAR(36)` | - | Sí |
| `corrected_at` | `DATETIME` | - | Sí |
| `notes` | `TEXT` | - | Sí |
| `created_at` | `DATETIME` | - | No |

**Índices:**
- `idx_load_intervals_device_time`: (`device_id`, `start_at`)
- `idx_load_intervals_load_time`: (`load_id`, `start_at`)

### Tabla `loads`

| Columna | Tipo SQL | Clave / Restricción | Nullable |
| :--- | :--- | :--- | :--- |
| `id` | `VARCHAR(36)` | **PRIMARY KEY** | No |
| `device_id` | `VARCHAR(36)` | FK -> `devices.id` | No |
| `name` | `VARCHAR(120)` | - | No |
| `category` | `VARCHAR(30)` | - | No |
| `electrical_nature` | `VARCHAR(20)` | - | No |
| `operation_pattern` | `VARCHAR(30)` | - | No |
| `nameplate_power_w` | `NUMERIC(10, 2)` | - | Sí |
| `signature_power_w` | `NUMERIC(10, 2)` | - | Sí |
| `signature_dispersion_w` | `NUMERIC(10, 2)` | - | Sí |
| `signature_reactive_var` | `NUMERIC(10, 2)` | - | Sí |
| `signature_power_factor` | `NUMERIC(4, 3)` | - | Sí |
| `signature_on_seconds` | `NUMERIC(10, 1)` | - | Sí |
| `signature_on_mad_seconds` | `NUMERIC(10, 1)` | - | Sí |
| `signature_off_seconds` | `NUMERIC(10, 1)` | - | Sí |
| `signature_startup_peak_w` | `NUMERIC(10, 2)` | - | Sí |
| `signature_source` | `VARCHAR(20)` | - | Sí |
| `signature_samples` | `INTEGER` | - | Sí |
| `signature_measured_at` | `DATETIME` | - | Sí |
| `is_active` | `BOOLEAN` | - | No |
| `notes` | `TEXT` | - | Sí |
| `created_at` | `DATETIME` | - | No |
| `updated_at` | `DATETIME` | - | No |

**Índices:**
- `idx_loads_device`: (`device_id`)

### Tabla `machine_availability_events`

| Columna | Tipo SQL | Clave / Restricción | Nullable |
| :--- | :--- | :--- | :--- |
| `id` | `BIGINT` | **PRIMARY KEY** | No |
| `machine_id` | `VARCHAR(36)` | FK -> `machines.id` | No |
| `state` | `VARCHAR(10)` | - | No |
| `stop_type` | `VARCHAR(20)` | - | Sí |
| `start_at` | `DATETIME` | - | No |
| `end_at` | `DATETIME` | - | Sí |
| `avg_power_w` | `NUMERIC(10, 2)` | - | Sí |
| `origin` | `VARCHAR(20)` | - | No |
| `corrected_by_user_id` | `VARCHAR(36)` | - | Sí |
| `corrected_at` | `DATETIME` | - | Sí |
| `notes` | `TEXT` | - | Sí |

**Índices:**
- `idx_machine_availability_machine_open`: (`machine_id`, `end_at`)

### Tabla `machines`

| Columna | Tipo SQL | Clave / Restricción | Nullable |
| :--- | :--- | :--- | :--- |
| `id` | `VARCHAR(36)` | **PRIMARY KEY** | No |
| `device_id` | `VARCHAR(36)` | FK -> `devices.id`, UNIQUE | No |
| `name` | `VARCHAR(120)` | - | No |
| `on_threshold_w` | `NUMERIC(10, 2)` | - | Sí |
| `persistence_readings` | `INTEGER` | - | No |
| `persistence_seconds` | `NUMERIC(8, 2)` | - | No |
| `created_at` | `DATETIME` | - | No |
| `updated_at` | `DATETIME` | - | No |

### Tabla `oauth_clients`

| Columna | Tipo SQL | Clave / Restricción | Nullable |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | **PRIMARY KEY** | No |
| `client_id` | `VARCHAR(128)` | UNIQUE | No |
| `client_name` | `VARCHAR(128)` | - | No |
| `redirect_uris` | `TEXT` | - | No |
| `is_trusted` | `BOOLEAN` | - | No |
| `created_at` | `DATETIME` | - | No |

**Índices:**
- `ix_oauth_clients_client_id` (UNIQUE): (`client_id`)

### Tabla `oauth_codes`

| Columna | Tipo SQL | Clave / Restricción | Nullable |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | **PRIMARY KEY** | No |
| `code_hash` | `VARCHAR(64)` | UNIQUE | No |
| `client_id` | `VARCHAR(128)` | - | No |
| `user_id` | `VARCHAR(36)` | FK -> `users.id` | No |
| `organization_id` | `VARCHAR(36)` | - | Sí |
| `redirect_uri` | `VARCHAR(512)` | - | No |
| `code_challenge` | `VARCHAR(128)` | - | No |
| `code_challenge_method` | `VARCHAR(16)` | - | No |
| `scope` | `VARCHAR(256)` | - | No |
| `expires_at` | `DATETIME` | - | No |
| `used` | `BOOLEAN` | - | No |
| `created_at` | `DATETIME` | - | No |

**Índices:**
- `idx_oauth_codes_client_user`: (`client_id`, `user_id`)
- `idx_oauth_codes_expires_at`: (`expires_at`)
- `ix_oauth_codes_code_hash` (UNIQUE): (`code_hash`)

### Tabla `oauth_refresh_tokens`

| Columna | Tipo SQL | Clave / Restricción | Nullable |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | **PRIMARY KEY** | No |
| `token_hash` | `VARCHAR(64)` | UNIQUE | No |
| `client_id` | `VARCHAR(128)` | - | No |
| `user_id` | `VARCHAR(36)` | FK -> `users.id` | No |
| `organization_id` | `VARCHAR(36)` | - | Sí |
| `scope` | `VARCHAR(256)` | - | No |
| `expires_at` | `DATETIME` | - | No |
| `revoked_at` | `DATETIME` | - | Sí |
| `created_at` | `DATETIME` | - | No |

**Índices:**
- `idx_oauth_refresh_tokens_client_user`: (`client_id`, `user_id`)
- `idx_oauth_refresh_tokens_expires_at`: (`expires_at`)
- `ix_oauth_refresh_tokens_token_hash` (UNIQUE): (`token_hash`)

### Tabla `organizations`

| Columna | Tipo SQL | Clave / Restricción | Nullable |
| :--- | :--- | :--- | :--- |
| `id` | `VARCHAR(36)` | **PRIMARY KEY** | No |
| `plan_id` | `VARCHAR(36)` | FK -> `plans.id` | Sí |
| `pro_expires_at` | `DATETIME` | - | Sí |
| `free_tier_mode` | `VARCHAR(30)` | - | No |
| `es_cooperativa` | `BOOLEAN` | - | No |
| `created_at` | `DATETIME` | - | No |
| `updated_at` | `DATETIME` | - | No |

### Tabla `plans`

| Columna | Tipo SQL | Clave / Restricción | Nullable |
| :--- | :--- | :--- | :--- |
| `id` | `VARCHAR(36)` | **PRIMARY KEY** | No |
| `name` | `VARCHAR(100)` | - | No |
| `description` | `TEXT` | - | No |
| `monthly_price_ars` | `NUMERIC(12, 2)` | - | No |
| `visibility` | `VARCHAR(20)` | - | No |
| `retention_days` | `INTEGER` | - | No |
| `granularity_minutes` | `INTEGER` | - | No |
| `max_devices` | `INTEGER` | - | No |
| `notification_channels` | `JSON` | - | No |
| `created_at` | `DATETIME` | - | No |
| `updated_at` | `DATETIME` | - | No |

### Tabla `scheduled_stops`

| Columna | Tipo SQL | Clave / Restricción | Nullable |
| :--- | :--- | :--- | :--- |
| `id` | `VARCHAR(36)` | **PRIMARY KEY** | No |
| `machine_id` | `VARCHAR(36)` | FK -> `machines.id` | No |
| `start_at` | `DATETIME` | - | No |
| `end_at` | `DATETIME` | - | No |
| `reason` | `VARCHAR(250)` | - | No |
| `created_by_user_id` | `VARCHAR(36)` | - | Sí |
| `created_at` | `DATETIME` | - | No |

**Índices:**
- `idx_scheduled_stops_machine_range`: (`machine_id`, `start_at`, `end_at`)

### Tabla `telemetria_anomalias`

| Columna | Tipo SQL | Clave / Restricción | Nullable |
| :--- | :--- | :--- | :--- |
| `id` | `BIGINT` | **PRIMARY KEY** | No |
| `device_id` | `VARCHAR(36)` | FK -> `devices.id` | No |
| `recorded_at` | `DATETIME` | - | No |
| `error_s` | `FLOAT` | - | No |
| `flag_tipo` | `VARCHAR(15)` | - | No |
| `contador_consecutivos` | `INTEGER` | - | No |
| `estado` | `VARCHAR(8)` | - | No |
| `creado_en` | `DATETIME` | - | No |
| `actualizado_en` | `DATETIME` | - | No |

**Índices:**
- `idx_anomalias_device_recorded`: (`device_id`, `recorded_at`)
- `idx_anomalias_estado`: (`estado`)

### Tabla `telemetry_energy`

| Columna | Tipo SQL | Clave / Restricción | Nullable |
| :--- | :--- | :--- | :--- |
| `id` | `BIGINT` | **PRIMARY KEY** | No |
| `device_id` | `VARCHAR(36)` | FK -> `devices.id` | No |
| `recorded_at` | `DATETIME` | - | No |
| `net_active_energy_kwh` | `NUMERIC(14, 3)` | - | Sí |
| `net_reactive_energy_kvarh` | `NUMERIC(14, 3)` | - | Sí |
| `imported_active_energy_kwh` | `NUMERIC(14, 3)` | - | Sí |
| `exported_active_energy_kwh` | `NUMERIC(14, 3)` | - | Sí |
| `imported_reactive_energy_kvarh` | `NUMERIC(14, 3)` | - | Sí |
| `exported_reactive_energy_kvarh` | `NUMERIC(14, 3)` | - | Sí |
| `source` | `VARCHAR(16)` | - | Sí |
| `created_at` | `DATETIME` | - | No |

**Índices:**
- `idx_telemetry_energy_dev_time`: (`device_id`, `recorded_at`)
- `idx_telemetry_energy_time`: (`recorded_at`)
- `uq_energy_dev_time` (UNIQUE): (`device_id`, `recorded_at`)

### Tabla `telemetry_instantaneous`

| Columna | Tipo SQL | Clave / Restricción | Nullable |
| :--- | :--- | :--- | :--- |
| `id` | `BIGINT` | **PRIMARY KEY** | No |
| `device_id` | `VARCHAR(36)` | FK -> `devices.id` | No |
| `recorded_at` | `DATETIME` | - | No |
| `voltage_r` | `NUMERIC(6, 2)` | - | Sí |
| `current_r` | `NUMERIC(6, 2)` | - | Sí |
| `active_power_r` | `NUMERIC(10, 2)` | - | Sí |
| `reactive_power_r` | `NUMERIC(10, 2)` | - | Sí |
| `apparent_power_r` | `NUMERIC(10, 2)` | - | Sí |
| `power_factor_r` | `NUMERIC(4, 2)` | - | Sí |
| `voltage_s` | `NUMERIC(6, 2)` | - | Sí |
| `current_s` | `NUMERIC(6, 2)` | - | Sí |
| `active_power_s` | `NUMERIC(10, 2)` | - | Sí |
| `reactive_power_s` | `NUMERIC(10, 2)` | - | Sí |
| `apparent_power_s` | `NUMERIC(10, 2)` | - | Sí |
| `power_factor_s` | `NUMERIC(4, 2)` | - | Sí |
| `voltage_t` | `NUMERIC(6, 2)` | - | Sí |
| `current_t` | `NUMERIC(6, 2)` | - | Sí |
| `active_power_t` | `NUMERIC(10, 2)` | - | Sí |
| `reactive_power_t` | `NUMERIC(10, 2)` | - | Sí |
| `apparent_power_t` | `NUMERIC(10, 2)` | - | Sí |
| `power_factor_t` | `NUMERIC(4, 2)` | - | Sí |
| `total_active_power` | `NUMERIC(12, 2)` | - | Sí |
| `total_reactive_power` | `NUMERIC(12, 2)` | - | Sí |
| `total_apparent_power` | `NUMERIC(12, 2)` | - | Sí |
| `total_power_factor` | `NUMERIC(4, 2)` | - | Sí |
| `desbalance_tension_porcentaje` | `NUMERIC(5, 2)` | - | Sí |
| `current_n` | `NUMERIC(6, 2)` | - | Sí |
| `voltage_linea_V` | `NUMERIC(6, 2)` | - | Sí |
| `tension_neutro_estimada` | `NUMERIC(6, 2)` | - | Sí |
| `thd_v_r` | `NUMERIC(5, 2)` | - | Sí |
| `thd_i_r` | `NUMERIC(5, 2)` | - | Sí |
| `thd_v_s` | `NUMERIC(5, 2)` | - | Sí |
| `thd_i_s` | `NUMERIC(5, 2)` | - | Sí |
| `thd_v_t` | `NUMERIC(5, 2)` | - | Sí |
| `thd_i_t` | `NUMERIC(5, 2)` | - | Sí |
| `thd_v_promedio_porcentaje` | `NUMERIC(5, 2)` | - | Sí |
| `thd_i_total_porcentaje` | `NUMERIC(5, 2)` | - | Sí |
| `es_dato_confiable` | `BOOLEAN` | - | No |
| `created_at` | `DATETIME` | - | No |

**Índices:**
- `idx_telemetry_inst_dev_time`: (`device_id`, `recorded_at`)
- `idx_telemetry_inst_time`: (`recorded_at`)

### Tabla `user_facility_access`

| Columna | Tipo SQL | Clave / Restricción | Nullable |
| :--- | :--- | :--- | :--- |
| `user_id` | `VARCHAR(36)` | **PRIMARY KEY**, FK -> `users.id` | No |
| `facility_id` | `VARCHAR(36)` | **PRIMARY KEY** | No |
| `can_switch` | `BOOLEAN` | - | No |
| `created_at` | `DATETIME` | - | No |

**Índices:**
- `idx_user_facility_access_facility`: (`facility_id`)

### Tabla `users`

| Columna | Tipo SQL | Clave / Restricción | Nullable |
| :--- | :--- | :--- | :--- |
| `id` | `VARCHAR(36)` | **PRIMARY KEY** | No |
| `username` | `VARCHAR(150)` | UNIQUE | No |
| `password_hash` | `VARCHAR(255)` | - | No |
| `role` | `VARCHAR(20)` | - | No |
| `is_active` | `BOOLEAN` | - | No |
| `totp_secret` | `VARCHAR(255)` | - | Sí |
| `totp_enabled` | `BOOLEAN` | - | No |
| `totp_backup_codes` | `JSON` | - | Sí |
| `sesiones_revocadas_antes_de` | `DATETIME` | - | Sí |
| `organization_id` | `VARCHAR(36)` | FK -> `organizations.id` | Sí |
| `created_at` | `DATETIME` | - | No |
| `updated_at` | `DATETIME` | - | No |

**Índices:**
- `ix_users_username` (UNIQUE): (`username`)

### Tabla `webhook_events`

| Columna | Tipo SQL | Clave / Restricción | Nullable |
| :--- | :--- | :--- | :--- |
| `id` | `VARCHAR(36)` | **PRIMARY KEY** | No |
| `provider` | `VARCHAR(30)` | - | No |
| `event_id` | `VARCHAR(100)` | - | No |
| `processed_at` | `DATETIME` | - | No |

## 3. Matriz de Políticas de Retención y Granularidad (Modelo Activo PRO 60d / Free)

Conforme a la directiva comercial en `docs/to_www-datamaq.md` y al servicio `PoliticaSuscripcionService`:

| Tabla | Categoría | Free Privado Básico (Default) | Vitrina Pública Anónima (Opt-in) | Versión PRO (60d Activa) | Estrategia de Purga |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `telemetry_instantaneous` | Series Temporales (V, I, P, FP) | 7 días (gran. horaria/5m) | 30 días (gran. 5 min / 1s) | 365 días (máxima resolución) | Batched `DELETE ... LIMIT 1000` |
| `telemetry_energy` | Acumulados de Energía (kWh) | 7 días | 30 días | 365 días | Batched `DELETE ... LIMIT 1000` |
| `device_status_logs` | Diagnóstico de Conectividad (Wi-Fi, IP) | 7 días | 15 días | 30 días | Batched `DELETE ... LIMIT 1000` |
| `device_alerts` (Resueltas) | Incidentes Cerrados | 14 días | 30 días | 365 días | `WHERE is_resolved = TRUE AND resolved_at < corte` |
| `device_alerts` (Activas) | Incidentes Abiertos | **Indefinida (0 borrado)** | **Indefinida (0 borrado)** | **Indefinida (0 borrado)** | **Preservadas permanentemente** |

