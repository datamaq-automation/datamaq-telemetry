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

### Contexto de negocio en `error_negocio` (sujeto del error)

- `DominioAuthException` (`src/domain/auth/exceptions.py`) gana un atributo opcional
  `usuario: str | None = None` (retrocompatible): las excepciones de negocio pueden
  transportar el sujeto afectado sin acoplar el dominio al logging.
- `AutenticarUsuarioUseCase.login` adjunta el nombre **normalizado** (`NombreUsuario`)
  al lanzar `DemasiadosIntentosError`, `CredencialesInvalidasError` (usuario
  inexistente y contraseña incorrecta) y `UsuarioInactivoError`.
- `manejar_error_http` lee `getattr(exc, "usuario", None)`; si no es `None`, añade
  `usuario` al evento (`error_negocio` y `error_interno`). Si es `None`, la clave
  **no** se emite (no contamina errores sin contexto). `redactar_secretos`
  (`logger.py`) ya redacta `contrasena`/`password`/`token`/`secret`/`clave` como
  doble barrera; la clave `usuario` no es sensible y se emite tal cual.

### Log de rutas inexistentes (`404`)

- `manejar_404(request, exc)` (`src/infrastructure/fastapi/error_handler.py`):
  handler de `StarletteHTTPException` registrado en `create_app`. Loguea
  `ruta_no_encontrada` (warning, con `metodo`, `path`, `request_id`) **solo** si
  `status_code == 404 and detail == "Not Found"`. Los `404` de negocio (p. ej.
  `DispositivoNoEncontradoError`, ya logueados como `error_negocio`) no duplican.
  Reconstruye la respuesta estándar de Starlette (`JSONResponse` + `headers`).

### Auditoría de login exitoso

- `auth_router.login` loguea `login_exitoso` (info) con `usuario=dto.usuario` y
  `request_id` tras el login correcto. Nunca se loguea `contrasena`.

## 5. Matriz de Pruebas (RED Suite)

| # | Escenario | Assert |
|---|---|---|
| E1 | excepción no mapeada en endpoint | respuesta 500 con header `X-Request-ID`; log `error_interno` con `request_id` igual al header |
| E2 | dos requests con error | `X-Request-ID` distintos |
| E3 | excepción de negocio (credenciales inválidas) | 401; log `error_negocio` warning sin `exc_info`/`exception` ni campo `contrasena` |
| E4 | mapeo de errores independiente del modo | `manejar_error_http` mapea `CredencialesInvalidasError`→401, `DemasiadosIntentosError`→429, `Exception`→500 (sin settings) |
| E5 | error de negocio con `usuario` | 401; log `error_negocio` incluye `usuario=<valor>` y no incluye `contrasena` |
| E6 | error de negocio sin `usuario` | log `error_negocio` **sin** la clave `usuario` |
| E7 | `DemasiadosIntentosError` con `usuario` | 429; log `error_negocio` incluye `usuario` |
| E8 | login fallido (usuario inexistente) | `CredencialesInvalidasError` con `usuario` normalizado (`" Operador "` → `"operador"`) |
| E9 | ruta inexistente | 404; log `ruta_no_encontrada` con `metodo`, `path` y `request_id` |
| E10 | 404 de negocio (`DispositivoNoEncontradoError`) | log `error_negocio` presente; `ruta_no_encontrada` ausente |
| E11 | login exitoso | log `login_exitoso` con `usuario` y sin `contrasena` |

## 6. Criterios del Gauntlet

`.venv/bin/pytest`, `.venv/bin/ruff check .`, `.venv/bin/ruff format --check .`, `.venv/bin/pyright src/`, `.venv/bin/python scripts/verify_architecture.py`. Reglas inmutables: imports absolutos `from src...`, `__init__.py` de 0 bytes, prohibidos `# type: ignore`/`# noqa`/`cast(Any, ...)`/`@pytest.mark.skip`.
