# Spec: Migraciones de esquema con Alembic

## 1. Objetivo y Contexto

Adoptar **Alembic** como mecanismo oficial de migraciones de esquema de la base de datos MySQL, y reconciliar la base de datos local existente (drift ORM vs. tabla física).

**Problema:** `Base.metadata.create_all()` (usado en `create_tables_if_needed()` y `scripts/init_db.py`) solo crea tablas ausentes; **nunca altera tablas existentes**. Cambios de esquema aplicados al ORM sin migración dejaron la BD local desincronizada, provocando errores en runtime como `Unknown column 'users.role'`.

**Drift real confirmado (MySQL 8.4.11, BD `datamaq_telemetry`):**

| Tabla | Columna faltante | Impacto |
| :--- | :--- | :--- |
| `users` | `role` (VARCHAR(20) NOT NULL DEFAULT 'operador') | Bloquea login/auth (500) |
| `organizations` | `plan_id` (VARCHAR(36) NULL, FK a `plans.id`) | Bloquea queries de organizaciones |
| varias | índices compuestos (`idx_telemetry_inst_dev_time`, `idx_telemetry_inst_time`, `idx_telemetry_energy_dev_time`, `idx_telemetry_energy_time`, `idx_device_status_dev_time`, `idx_device_status_time`, `idx_alerts_dev_resolved`, `idx_alerts_resolved_purge`) | drift menor (rendimiento) |

**Alcance:** infraestructura de migración (`alembic.ini`, `alembic/`, migraciones). **Sin cambios en `src/`** (se mantiene `create_tables_if_needed` como fallback no-op). La migración se ejecuta manualmente o vía `scripts/init_db.py`; no en el arranque del servidor.

## 2. Dominio & Puertos

- Sin cambios en `src/domain/` ni `src/application/` (esto es infraestructura de datos).
- Fuente de verdad del esquema: `src/infrastructure/sqlalchemy/models.py` (`Base.metadata`).
- `alembic/env.py` debe resolver `target_metadata = Base.metadata` y la URL de conexión desde `get_settings().database_url`, con override opcional por variable de entorno `DATABASE_URL` (necesaria para pruebas con SQLite y para el autogenerate contra una BD temporal).

## 3. Casos de Uso & Flujo

1. **BD nueva:** `alembic upgrade head` → aplica `0001_initial_schema` (esquema completo) y `0002_reconcile_legacy` (no-op por guardas).
2. **BD legacy (drift):** `alembic stamp 0001_initial_schema` + `alembic upgrade head` → aplica solo `0002` (ALTERs idempotentes).
3. **Autogenerate:** `DATABASE_URL=<tmp> alembic revision --autogenerate -m "..."` genera el diff metadata↔BD.
4. **Downgrade:** `alembic downgrade -1` revierte la última revisión.

**Regla de idempotencia:** las migraciones de reconciliación (`0002`) deben verificar la existencia de columnas/índices vía `sqlalchemy.inspect(bind)` (portable MySQL/SQLite) y aplicar el cambio solo si falta. **Prohibido** SQL crudo específico de un dialecto (p. ej. `information_schema`) que rompa la portabilidad a SQLite en tests.

## 4. Matriz de Pruebas (RED Suite)

`tests/unit/test_migraciones.py`:

| Escenario BDD | Contrato |
| :--- | :--- |
| Dado `env.py` con `DATABASE_URL` set → URL usada | `env.py` setea `sqlalchemy.url` desde `DATABASE_URL` (override) |
| Dado `env.py` sin `DATABASE_URL` → URL de settings | `env.py` usa `get_settings().database_url` |
| Dado SQLite vacío, `upgrade head` | `inspect` detecta las 9 tablas del metadata |
| Dado `users` legacy sin `role`, `stamp 0001` + `upgrade head` | `role` presente con default `operador` |
| Dado `organizations` legacy sin `plan_id`, `upgrade head` | `plan_id` presente |
| Dado `device_status_logs` con datos y sin `wifi_calidad`, `upgrade head` | `wifi_calidad` presente (no aplica si ya existe) |
| Dado BD ya reconciliada, `upgrade head` de nuevo | sin error (idempotencia) |
| Dado `upgrade head`, `downgrade -1` | revierte la última revisión sin error |

## 5. Criterios del Gauntlet

- `.venv/bin/pytest tests/unit/` → 100% aprobados, cobertura de `src/` ≥ 85% (Alembic no toca `src/`; sin impacto).
- `bash scripts/pre-push.sh` → Exit Code 0 (etapas 1-4).
- `ruff check .` y `ruff format --check .` → 0 errores (los archivos de migración y `env.py` deben pasar estilo).
- `pyright` (etapa 3) → 0 diagnósticos en `src/` (sin cambios en `src/`).
