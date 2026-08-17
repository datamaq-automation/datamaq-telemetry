# Spec — Observabilidad de Errores HTTP (observabilidad)

## 1. Objetivo y Contexto

Hacer visible y correlacionable todo error HTTP. Caso disparador: el `500` del login era una caja negra — los routers capturan `Exception`, la convierten vía `ErrorPresenter` en `HTTPException(500)` y esta **no pasa** por el handler global `manejar_excepcion_no_mapeada`, por lo que no se registraba ningún log. Además, el frontend ya parsea el header `X-Request-ID` (`app-datamaq/src/core/http/client.ts`) pero el backend no lo emite (D-03 pendiente en `docs/contrato-auth.md`).

## 2. Dominio y Puertos

Sin cambios en dominio/aplicación. `ErrorPresenter` permanece agnóstico (sin logging).

## 3. Casos de Uso y DTOs

Sin cambios.

## 4. Infraestructura

- `RequestIdMiddleware` (`src/infrastructure/fastapi/middleware.py`): genera `request_id` (uuid4 hex) por request, lo vincula a `structlog.contextvars` y lo emite en el header `X-Request-ID` de toda respuesta.
- `manejar_error_http(exc)` (`src/infrastructure/fastapi/error_handler.py`): centraliza el patrón try/except de los routers. `code, err = ErrorPresenter.presentar_excepcion(exc)`; si `code >= 500` loguea `error_interno` con `exc_info=True`; si no, `error_negocio` (warning) con `tipo`/`codigo`. Incluye `request_id` (leído de contextvars) y eleva `HTTPException(status_code=code, detail=err["mensaje"])`.
- Los 6 routers con try/except (auth, system, telemetria, planes, alertas, dispositivos, organizaciones) delegan en `manejar_error_http` y dejan de importar `ErrorPresenter`/`HTTPException`.
- `create_app(settings: Settings | None = None)`: recibe settings inyectados (composition root); si es `None`, usa `get_settings()` (compatibilidad). Registra `RequestIdMiddleware`.
- `auth_router` recibe settings vía `Depends(get_settings_dep)` en lugar de llamar `get_settings()` dentro del handler.
- `docs/contrato-auth.md`: documenta la emisión de `X-Request-ID` (D-03).

## 5. Matriz de Pruebas (RED Suite)

| # | Escenario | Assert |
|---|---|---|
| E1 | excepción no mapeada en endpoint | respuesta 500 con header `X-Request-ID`; log `error_interno` con `request_id` igual al header |
| E2 | dos requests con error | `X-Request-ID` distintos |
| E3 | excepción de negocio (credenciales inválidas) | 401; log `error_negocio` warning sin `exc_info`/`exception` ni campo `contrasena` |
| E4 | mapeo de errores independiente del modo | `manejar_error_http` mapea `CredencialesInvalidasError`→401, `DemasiadosIntentosError`→429, `Exception`→500 (sin settings) |

## 6. Criterios del Gauntlet

`venv/bin/pytest`, `venv/bin/ruff check .`, `venv/bin/ruff format --check .`, `venv/bin/pyright src/`, `venv/bin/python scripts/verify_architecture.py`. Reglas inmutables: imports absolutos `from src...`, `__init__.py` de 0 bytes, prohibidos `# type: ignore`/`# noqa`/`cast(Any, ...)`/`@pytest.mark.skip`.
