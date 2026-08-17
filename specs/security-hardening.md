# Spec G — Remediación de Hallazgos de Auditoría de Seguridad (security-hardening)

## 1. Objetivo y Contexto

Remedia los hallazgos de la auditoría de seguridad posterior al endurecimiento (Spec F). Evidencia recogida por exploración del código. Decisiones confirmadas: (1) WebSocket `/ws/live` se documenta como stream global — no se filtra por organización en esta iteración; (2) rotación de secretos vía clave dual `API_SECRET_KEY_ANTERIOR`; (3) CORS se corrige en `.env.example`; (4) clave autogenerada en DEBUG se documenta como dev-only.

| ID | Hallazgo | Severidad | Remediación |
|---|---|---|---|
| R1 | Rate limiter roto a nivel HTTP (instancia por request → nunca 429) + sin tope de memoria | CRÍTICA | G1 |
| R2 | `AUTH_REQUIRED=False` con `DEBUG=False` no validado | CRÍTICA | G2 |
| R3 | Sin exception handler global (500 no loguea traceback vía structlog) | ALTA | G3 |
| R4 | Sin headers de seguridad (HSTS/CSP/X-Content-Type/X-Frame) | ALTA | G4 |
| R6 | Sin rotación de secretos (una sola clave) | MEDIA | G5 |
| R7 | `verificar()` no valida `alg == HS256` | MEDIA | G5 |
| R8 | `.env.example` con `CORS_ORIGINS=*` y `DEBUG=True` | MEDIA | G2 |
| R9 | Mosquitto sin TLS (`allow_anonymous true`, listener 8883 comentado) | MEDIA | G6 |
| R5 | WS `/ws/live` global (sin filtro por organización) | DOCUMENTAR | G6 |

## 2. Dominio y Puertos

- `RateLimiterService` (`src/domain/auth/services.py`): gana **eviction por tope de claves** (`MAX_CLAVES`), mantiene ventana deslizante por clave.
- `GeneradorTokenPort.generar(...)` sin cambios. La verificación JWT con clave dual es infraestructura, no dominio.

## 3. Casos de Uso y DTOs

Sin cambios en DTOs. `AutenticarUsuarioUseCase` sigue recibiendo `rate_limiter` por inyección.

## 4. Infraestructura

- **G1:** factory `get_rate_limiter()` con `@lru_cache` en `src/infrastructure/fastapi/dependencies.py` (singleton de proceso, igual que `global_event_broadcaster`). `get_auth_controller` consume la factory.
- **G2:** `Settings.validar_postura_seguridad` rechaza `DEBUG=False` + `AUTH_REQUIRED=False`. `.env.example` sin `*`, sin placeholder débil, con `DEBUG=False`, `AUTH_REQUIRED=True`, `MQTT_TLS_ENABLED=True`.
- **G3:** `app.add_exception_handler(Exception, ...)` en `server.py` loguea traceback con structlog (redactado) y responde 500 genérico sin exponer stack.
- **G4:** middleware de headers de seguridad (HSTS solo prod, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, CSP configurable).
- **G5:** `verificar()` exige `alg == "HS256"`; soporte de clave dual `API_SECRET_KEY` (firma) + `API_SECRET_KEY_ANTERIOR` (verificación).
- **G6:** `deploy/mosquitto/mosquitto.conf` activa TLS 8883 y `allow_anonymous false`; `docs/contrato-auth.md` documenta WS global.

## 5. Matriz de Pruebas (RED Suite)

| Fase | Tests |
|---|---|
| G1 | `get_rate_limiter()` devuelve la misma instancia (singleton); eviction por `MAX_CLAVES` elimina claves más antiguas; el limiter compartido bloquea tras exceder intentos |
| G2 | `Settings(DEBUG=False, AUTH_REQUIRED=False)` lanza `ValueError`; `.env.example` no contiene `*` ni `DEBUG=True`; defaults seguros |
| G3 | branch 500 de `ErrorPresenter`; excepción no mapeada responde 500 sin stack y loguea |
| G4 | headers presentes en respuesta; HSTS ausente con `DEBUG=True`, presente con `DEBUG=False` |
| G5 | token con `alg: none`/`RS256` rechazado; token firmado con clave anterior válido |
| G6 | mosquitto.conf con TLS activo y `allow_anonymous false`; contrato documenta WS global |

## 6. Criterios del Gauntlet

`venv/bin/pytest --cov=src`, `venv/bin/ruff check .`, `venv/bin/ruff format --check .`, `venv/bin/pyright src/`, `venv/bin/python scripts/verify_architecture.py`. Reglas inmutables: imports absolutos `from src...`, `__init__.py` de 0 bytes, prohibidos `# type: ignore`/`# noqa`/`cast(Any, ...)`/`@pytest.mark.skip`.
