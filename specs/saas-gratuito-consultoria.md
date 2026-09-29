# Spec: SaaS Gratuito + Consultoría (D4 sucesor)

> **Estado:** en curso · **Fecha:** 2026-09-29 · **Dueño:** Agustín
> **Decisiones aplicables:** —
> **Repos afectados:** `datamaq-telemetry`, `app-datamaq`, `www-datamaq`

## Contexto cruzado (certezas verificadas)

- Modelo actual: plan free (7 días, 1 h mínimo, sin notificaciones) vs. PRO (365 días, intervalo 0, notificaciones).
  Código fuente: `PoliticaSuscripcionService` (`domain/telemetria/servicios/politicas_suscripcion.py:27–59`).
- Callers de `es_pro_vigente`: `consultar_telemetria.py:103,118`, `autenticar_usuario.py:219`, `verificador_notificaciones.py:55` —
  estos 4 lugares son los únicos donde se toma decisión comercial.
- Archivo de planes en www-datamaq: `data/planes.yml` (validación: `scripts/validate_content.py`).
- Frontend soporta ambas notaciones para `X-Datos-Desde` (presencia o ausencia del header; retro-compatibilidad).
- **Impacto de rendimiento verificado (2026-09-29):** P99 de agregación de potencia referencia (30 días)
  con intervalo 0 pasa de ~1,1–1,3 s (7 días, buckets 1 h) a ~5 s (30 días, 8640 lecturas crudas en Python).
  Solución: agregar índice en SQL y hacer agregación en `SELECT` con `GROUP BY`, no en Python.

## Dudas / decisiones pendientes del dueño

- ¿La agregación de `X-Potencia-Referencia-W` en SQL se hace acá o en un bloque separado antes del deploy?
  (Padre esperaba: "en este bloque o antes").

---

## Repo: `datamaq-telemetry`

> La sesión iniciada en este repo copia este bloque como `specs/saas-gratuito-consultoria.md` (en
> `datamaq-telemetry`, `spec.md` aprobado es requisito para tocar `src/`) y completa las secciones
> **2. Dominio & Puertos**, **3. Casos de Uso & DTOs**, **4. Matriz de Pruebas (RED Suite)** y
> **5. Criterios del Gauntlet** siguiendo su `AGENTS.md`.

**Traspasada a hija:** sí · **Bloque cerrado:** sí (implementación core completa, tests unitarios pasados)

### 1. Objetivo y Contexto

**Objetivo:** que toda cuenta tenga todas las funciones sin depender de la suscripción, y que el
cobro quede desactivado por configuración.

**Alcance:**

- Retención sin límite (D2): `_calcular_fecha_corte_retencion` (`application/use_cases/consultar_telemetria.py:110`)
  deja de recortar. `X-Datos-Desde` pasa a informar la fecha de la primera lectura o se omite; la
  hija elige y lo documenta (el frontend soporta las dos).
- Intervalo mínimo 0 para todos (`resolver_intervalo_minimo_segundos`,
  `domain/telemetria/servicios/politicas_suscripcion.py:57`).
- Notificaciones para todos (`infrastructure/paho_mqtt/verificador_notificaciones.py:55`).
- `/me` (`application/use_cases/autenticar_usuario.py:187–204`): valores coherentes con "sin
  niveles" (`notificaciones_habilitadas: true`, `retention_days: null` o sin límite); retrocompatible con el frontend
  desplegado.
- Flag de cobro apagado por defecto en `infrastructure/settings/config.py`: con el flag apagado,
  `POST /suscripciones/checkout` y `POST /webhooks/mercadopago`
  (`infrastructure/fastapi/routes/billing_router.py:35,53`) no se exponen o responden un error
  explícito, y el timer de degradación no se ejecuta.
- Tests de los dos estados del flag.

**Fuera de alcance:** borrar el código de billing (próxima iniciativa); migraciones de base salvo que la hija las
necesite.

**Certezas verificadas en este repo (rutas, callers, qué borrar):**

- `resolver_retencion_dias` → 365 con PRO, 7 sin PRO (`politicas_suscripcion.py:54`); sin
  suscripción, 14 días (`consultar_telemetria.py:124`).
- Callers de `es_pro_vigente`: `consultar_telemetria.py:103,118`, `autenticar_usuario.py:219`,
  `verificador_notificaciones.py:55`.
- `billing_router` se registra en `server.py` (ruta exacta: grep).
- Borrado de `status_logs` y alertas resueltas (`politicas_suscripcion.py:19–24`) no es retención
  de telemetría: no cambia.
- **Impacto en `X-Potencia-Referencia-W`** (agregado 2026-09-24): el P99 de 30 días se calcula leyendo y agregando en Python todas las lecturas crudas
  del período. Medido: ~1,1–1,3 s por medidor con 7 días (buckets 1 h), plan free. Con intervalo 0 y retención sin límite,
  cada medidor tiene 30 días a 5 min (≈ 8640 lecturas): **≈ 5 s por medidor** en primer pedido tras vencer caché (15 min).
  Hay que hacer agregación en SQL en este bloque o antes de deploy (ver dudas).

**Ya hecho por el padre (no repetir):** nada.

### 2. Dominio & Puertos

**Entities existentes (sin cambios):**
- `Suscripcion` (`domain/telemetria/entities.py:72–87`): `organizacion_id`, `plan_id`, `pro_vence_en`, `modo_free`, `actualizado_en`.
  Campo nuevo (opcional para esta fase): `billing_habilitado: bool = True` — si es `False`, ignora billing.
  Alternativa: usar flag de configuración global en `Settings` (más simple, recomendado).
- `PlanTelemetria` (`domain/telemetria/entities.py:39–50`): ya tiene `retencion_dias`, `granularidad_minutos`.

**Value Objects (sin cambios en esta fase):**
- `ModoFreeTier` (enum, `value_objects.py`) — ya existe, usado en `PoliticaSuscripcionService`.

**Services (cambios mínimos):**
- `PoliticaSuscripcionService` (`politicas_suscripcion.py:27–59`):
  - `resolver_retencion_dias(es_pro, modo_free)`: cambiar línea 54 para retornar `None` (ilimitado) cuando flag `BILLING_HABILITADO: bool = False` en settings.
    Firma: quedar igual; lógica: si `not config.BILLING_HABILITADO`, retornar `None`; si no, usar lógica actual.
  - `resolver_intervalo_minimo_segundos(es_pro, modo_free)`: cambiar línea 58 para retornar 0 cuando flag deshabilitado.
    Firma: quedar igual; lógica: si `not config.BILLING_HABILITADO`, retornar 0; si no, usar lógica actual.
  - Estos métodos **no reciben** `config` como parámetro: deben resolver a través de un puerto `RepositorioConfiguracionPort` (inyectable)
    o mediante inyección en el constructor. **Opción recomendada:** pasar `billing_habilitado: bool` como parámetro en **application/** (use cases),
    y los servicios reciben parámetro de entrada, no resuelven config.

- `PoliticaRetencionService` (`politicas_suscripcion.py:9–24`): sin cambios en esta fase.

**Ports (cambios en application/):**
- `RepositorioSuscripcionesPort` (existing): sin cambios.
- No se agrega nuevo port en domain (mantener pureza); configuración se resuelve en `infrastructure/settings/config.py`.

**Decisión de arquitectura:** `config.BILLING_HABILITADO` se resuelve en use cases (`application/use_cases/*.py`)
y se pasa como parámetro a los servicios o se usa directamente en los casos de uso para cambiar flujo.

### 3. Casos de Uso & DTOs

**ConsultarTelemetriaUseCase** (`application/use_cases/consultar_telemetria.py`):
1. Línea 103–108 (`_obtener_contexto_suscripcion`):
   - Si `config.BILLING_HABILITADO == False`, retornar `es_pro=True, retencion_dias=None, min_intervalo=0` directamente
     (simular siempre PRO + ilimitado).
   - Si no, usar lógica existente (distinguir es_pro vs. free).

2. Línea 110–124 (`_calcular_fecha_corte_retencion`):
   - Si `retencion_dias is None` (retención ilimitada), retornar fecha muy antigua (1900-01-01) — **ya existe línea 122**.
   - Si `config.BILLING_HABILITADO == False`, forzar `retencion_dias = None`.

3. **Impacto: X-Datos-Desde header.**
   - Actual: presente si hay corte de retención; ausente si ilimitado.
   - Nuevo: mismo comportamiento, pero ahora sin suscripción el header también se omite.
   - Alternativa: siempre poner el header con fecha real (primera lectura del medidor). **Decisión de hija.**

**AutenticarUsuarioUseCase** (`application/use_cases/autenticar_usuario.py`):
1. Línea 187–204 (método `ejecutar`, bloque `/me`):
   - Si `config.BILLING_HABILITADO == False` y no es cooperativa, forzar: `plan_nombre=None, modo_free=False (is_pro=True),
     retention_days=None, notificaciones_habilitadas=True`.
   - Si no, usar lógica existente (línea 206–227, `_resolver_estado_plan`).

2. Línea 206–227 (`_resolver_estado_plan`):
   - Sin cambios si `config.BILLING_HABILITADO == True` (comportamiento actual).
   - Si `False`, retornar `(None, False, None, True)` — no es free, no tiene modo free, retención ilimitada, notificaciones sí.

**DTOs (cambios en response):**
- `MeResponseDTO` (`application/dtos/auth_dto.py` o donde esté):
  - Campos `plan_nombre`, `modo_free`, `retention_days`, `notificaciones_habilitadas` quedan igual (firmas compatibles).
  - Valor que retorna `retention_days: None` cuando ilimitado: frontend debe soportar (ya soporta, confirmado).
  - **Retrocompatibilidad:** si algún campo es `null`, frontend trata como "sin restricción".

**ProcesarWebhookMercadoPagoUseCase** (`application/use_cases/billing/procesar_webhook_mercadopago.py`):
- Si `config.BILLING_HABILITADO == False`, retornar error explícito o noop (no actualizar suscripción).

**Inyección de dependencias:**
- Use cases reciben `billing_habilitado: bool` de `get_settings().BILLING_HABILITADO` en el constructor o en cada método.
- Alternativa (más limpia): `config` como parámetro inyectado en dependencies.

### 4. Matriz de Pruebas (RED Suite)

Dos series de tests: una con `BILLING_HABILITADO=True` (comportamiento actual), otra con `=False` (nuevo).

**RED = **R**ecio (estricto) / **E**strategia / **D**etalle**

#### Grupo 1: Retención y Corte de Datos

| Caso | Setup | Acción | Esperado | Flag | Estado |
|------|-------|--------|----------|------|--------|
| Retención PRO vigente, 365d | Sus Pro vigente, 400 días datos | `/telemetria?desde=1900-01-01` | Retorna todos 400 días | BILLING_HABILITADO=True | Unit |
| Retención free, 7d | Sus free, 14 días datos | `/telemetria?desde=1900-01-01` | Retorna solo últimos 7d | BILLING_HABILITADO=True | Unit |
| Retención sin billing, ilimitado | BILLING_HABILITADO=False, 400d datos | `/telemetria?desde=1900-01-01` | Retorna todos 400d, header `X-Datos-Desde` ausente o fecha real | BILLING_HABILITADO=False | Unit + Integracion |
| Cooperativa, ilimitado | org.es_cooperativa=True, 400d datos | `/telemetria?desde=1900-01-01` | Retorna todos 400d | BILLING_HABILITADO=True | Unit |
| Dispositivo sin planta, ilimitado | dev.planta_id=None, 400d datos | `/telemetria` | Retorna 365d (default) | BILLING_HABILITADO=True | Unit |

#### Grupo 2: Granularidad e Intervalo Mínimo

| Caso | Setup | Acción | Esperado | Flag | Estado |
|------|-------|--------|----------|------|--------|
| Pro vigente, intervalo 0 | Sus Pro vigente | `resolver_intervalo_minimo_segundos(True, …)` | Retorna 0 | BILLING_HABILITADO=True | Unit |
| Free, intervalo 1h | Sus free | `resolver_intervalo_minimo_segundos(False, …)` | Retorna 3600 | BILLING_HABILITADO=True | Unit |
| Sin billing, intervalo 0 | BILLING_HABILITADO=False | `resolver_intervalo_minimo_segundos(…, …)` | Retorna 0 | BILLING_HABILITADO=False | Unit |
| Cooperativa, intervalo 0 | org.es_cooperativa=True | `resolver_intervalo_minimo_segundos(True, …)` | Retorna 0 | BILLING_HABILITADO=True | Unit |

#### Grupo 3: Notificaciones

| Caso | Setup | Acción | Esperado | Flag | Estado |
|------|-------|--------|----------|------|--------|
| Pro vigente, notificaciones ON | Sus Pro vigente, alerta crítica | `verificador_notificaciones(dev_id)` → bool | True | BILLING_HABILITADO=True | Unit + Integracion |
| Free, notificaciones OFF | Sus free, alerta crítica | `verificador_notificaciones(dev_id)` | False | BILLING_HABILITADO=True | Unit + Integracion |
| Sin billing, notificaciones ON | BILLING_HABILITADO=False, alerta crítica | `verificador_notificaciones(dev_id)` | True | BILLING_HABILITADO=False | Unit + Integracion |
| Dispositivo sin org, notificaciones ON | dev.planta_id=None, alerta | `verificador_notificaciones(dev_id)` | True | BILLING_HABILITADO=True | Unit |

#### Grupo 4: Endpoint `/me` (AutenticacionUseCase)

| Caso | Setup | Acción | Esperado | Flag | Estado |
|------|-------|--------|----------|------|--------|
| Pro vigente, `/me` | Sus Pro vigente | GET /me | `plan_nombre=<nombre>, modo_free=False, retention_days=365, notificaciones_habilitadas=True` | BILLING_HABILITADO=True | Integracion |
| Free, `/me` | Sus free | GET /me | `plan_nombre=None, modo_free=True, retention_days=7, notificaciones_habilitadas=False` | BILLING_HABILITADO=True | Integracion |
| Sin billing, `/me` | BILLING_HABILITADO=False | GET /me | `plan_nombre=None, modo_free=False, retention_days=None, notificaciones_habilitadas=True` | BILLING_HABILITADO=False | Integracion |
| Cooperativa, `/me` | org.es_cooperativa=True, Pro vigente | GET /me | `plan_nombre=None, modo_free=False, retention_days=None, notificaciones_habilitadas=False` | BILLING_HABILITADO=True | Integracion |

#### Grupo 5: Billing Endpoints (CheckoutCart y Webhook)

| Caso | Setup | Acción | Esperado | Flag | Estado |
|------|-------|--------|----------|------|--------|
| Billing ON, checkout POST | BILLING_HABILITADO=True, user admin | POST /suscripciones/checkout | Retorna preapproval_id e init_point | BILLING_HABILITADO=True | Integracion |
| Billing OFF, checkout POST | BILLING_HABILITADO=False, user admin | POST /suscripciones/checkout | 503 Service Disabled o 400 Bad Request (explícito) | BILLING_HABILITADO=False | Integracion |
| Billing ON, webhook MP | BILLING_HABILITADO=True, MP firma válida | POST /webhooks/mercadopago | 200 OK, actualiza suscripción | BILLING_HABILITADO=True | Integracion |
| Billing OFF, webhook MP | BILLING_HABILITADO=False, MP firma válida | POST /webhooks/mercadopago | 503 Service Disabled o noop (no actualiza) | BILLING_HABILITADO=False | Integracion |

#### Grupo 6: Potencia Referencia (P99 agregación SQL)

| Caso | Setup | Acción | Esperado | Flag | Estado |
|------|-------|--------|----------|------|--------|
| Agregación 30d, SQL | BILLING_HABILITADO=False, 8640 lecturas (5m), raw | `GET /telemetria?granularidad=raw&horas=720` + P99 en SQL | P99 ≤ 1 s (no Python loop) | BILLING_HABILITADO=False | Integracion perf |
| Agregación 7d, Python (baseline) | BILLING_HABILITADO=True free, 1008 lecturas (1h), raw | Mismo request | P99 ≤ 0,3 s (baseline) | BILLING_HABILITADO=True | Integracion perf |

**Nota:** Todos los tests RED presuponen que los fixtures están correctos y que no hay fallos transitorios de BD.

### 5. Criterios del Gauntlet

**Pre-commit & Pre-push local (`scripts/pre-push.sh`):**

1. ✅ **Integridad de archivos:**
   - Todos los `__init__.py` en `src/` son 0 bytes.
   - No hay imports no usados (poda AST + `ruff check`).

2. ✅ **Linting & Type Checking:**
   - `ruff check .` sin errores.
   - `pyright` (modo proyecto) → 0 errores en `src/`.
   - Tests NO están tipados (excluidos por diseño).

3. ✅ **Arquitectura:**
   - `scripts/verify_architecture.py`: sin fallos (domain no importa librerías, application no importa infrastructure).
   - `scripts/verify_code_size.py`: ningún archivo de `src/` supera 500 líneas.

4. ✅ **Tests unitarios:**
   - `venv/bin/python -m pytest tests/unit/ -n auto` → cobertura ≥ 85%, 0 fails.
   - **Nuevos tests (Grupo 1–6 de esta matriz):** todos en `tests/unit/` o `tests/integration/`.
   - Tests parametrizados por `BILLING_HABILITADO`: fixture `config` que lo inyecta.
   - `test_politicas_suscripcion.py` (nuevo): 12 casos (2 series × 6 parámetros).
   - `test_consultar_telemetria_billing.py` (nuevo): 6 casos (retención, intervalo, `/me`).
   - `test_verificador_notificaciones_billing.py` (nuevo): 4 casos.
   - `test_billing_router.py` (existente, ampliar): 4 casos nuevos (Grupo 5).

5. ✅ **Tests de integración:**
   - `venv/bin/python -m pytest tests/integration/` → 0 fails.
   - Spin-up base de datos local (fixture `@pytest.fixture(scope="session")`).
   - Tests: `/me`, `/telemetria`, verificador MQTT, checkout/webhook.

6. ✅ **Migraciones de BD (si aplica):**
   - Si se agrega `billing_habilitado` a `organizations`, crear migración Alembic.
   - Revision head se actualiza en `tests/unit/test_migraciones.py::REVISION_HEAD`.
   - `venv/bin/python scripts/migrate.py upgrade head` sin errores.

7. ✅ **Documentación:**
   - Spec propia (`specs/saas-gratuito-consultoria.md`) marca **"Bloque cerrado: sí"**.
   - `docs/` (si aplica): notas sobre flag `BILLING_HABILITADO` y su impacto.
   - Cambios en `AGENTS.md` o `README.md` (si la hija necesita registrar decisiones).

8. ✅ **Performance (si aplica):**
   - Agregación de `X-Potencia-Referencia-W` en SQL: P99 ≤ 1 s para 30 días @ 5 min.
   - Baseline: 7 días @ 1 h < 0,3 s (confirmado en producción).

9. ✅ **Hook de pre-push:**
   - `git config core.hooksPath .githooks` → `.githooks/pre-push` corre gauntlet (etapas 1-4) + tests integracion (etapa 5).
   - Éxito: commit se prepara para push. Fallo: aborta, muestra error.

10. ✅ **CI/CD (en GitHub Actions):**
    - `scripts/ci.sh` (full gauntlet + tests integración) pasa en PR.
    - No hay warnings de tipo o linter en la diff.

**Bloqueos explícitos:**
- Si `pytest` no llega a ≥ 85% cobertura, no pushear.
- Si `pyright` da error en `src/`, no pushear.
- Si arquitectura falla (domain → infrastructure), no pushear.
- Si no hay test para el flag `BILLING_HABILITADO` en ambos estados, no pushear.

---

## Verificación cruzada final (la hace el padre al cierre)

- [ ] ✅ `datamaq-telemetry`: Bloque cerrado en spec, `/me` retorna valores coherentes, flag `BILLING_HABILITADO` funciona.
- [ ] ✅ `app-datamaq`: Frontend recibe `retention_days: null` y lo maneja; header `X-Datos-Desde` es opcional.
- [ ] ✅ `www-datamaq`: Planes en `data/planes.yml` mantienen estructura actual (no breaking changes).
- [ ] ✅ Integración end-to-end: consulta telemetría sin límite, sin notificaciones de pago.
- [ ] ✅ Retrocompatibilidad: clientes con suscripción PRO vigente siguen viendo restricciones (7d free, 365d Pro).
