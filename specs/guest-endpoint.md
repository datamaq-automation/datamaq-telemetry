# Spec G: Endpoint invitado (`POST /api/auth/guest`) + `Retry-After` en 429

> **⚠️ Superado.** El rol `invitado` y su endpoint se retiraron de `develop` y `main` (PR #74; compatibilidad temporal en PR #76). El estado vigente de roles y permisos está en [`specs/roles-y-permisos.md`](roles-y-permisos.md). Este documento se conserva como histórico; la parte de `Retry-After` en 429 no depende del rol.

## 1. Objetivo y Contexto

Proveer acceso anónimo de solo lectura mediante `POST /api/auth/guest`, que emite
un JWT `HS256` con `sub="invitado"`, `usuario="invitado"`, `rol="invitado"` **sin
consultar la base de datos** (el token es autosuficiente; `get_usuario_actual`
solo valida firma y expiración). Resuelve el `404` que hoy recibe el botón
"Entrar como invitado" de la SPA y elimina la necesidad de hardcodear credenciales
del seed en el cliente.

Además, agrega la cabecera `Retry-After` en las respuestas `429` (login y guest)
para que el frontend pueda mostrar un reintento preciso.

**Decisiones aprobadas:**

- **DEC-04:** se crea `POST /api/auth/guest` (público, sin body). Reemplaza a
  **DEC-03** (acceso invitado vía seed + login normal), que queda como camino
  alternativo/compatible. `scripts/seed_invitado.py` se mantiene.
- **Rate limiting por IP:** el endpoint guest limita por clave `ip:<host>`,
  reutilizando `LOGIN_MAX_INTENTOS` (5) y `LOGIN_VENTANA_SEGUNDOS` (300).
- **Retry-After (D-02):** `DemasiadosIntentosError` transporta
  `retry_after_seg`; el handler HTTP lo emite como cabecera `Retry-After`.
- **Sin BD en guest:** no se crea fila de usuario; el claim `rol="invitado"`
  habilita el scoping de solo lectura de `specs/roles-permisos.md`.
- **D-05 (`POST /api/usuarios`):** fuera de alcance (sprint propio).

## 2. Dominio y Puertos

Sin dependencias externas en `domain/auth/` (solo stdlib):

### `src/domain/auth/services.py`

- `RateLimiterService.segundos_restantes(clave: str) -> int`:
  - `0` si la clave está permitida (sin intentos o `len < max_intentos`).
  - si está bloqueada, `max(1, ceil(ventana_segundos - edad_del_intento_más_antiguo))`.

### `src/domain/auth/exceptions.py`

- `DemasiadosIntentosError(mensaje, usuario=None, retry_after_seg: int | None = None)`
  — añade atributo `retry_after_seg` (retrocompatible con el constructor previo).

## 3. Casos de Uso y DTOs

### `src/application/use_cases/autenticar_usuario.py`

- `login(dto, clave_limite: str | None = None) -> LoginResponseDTO`:
  - clave de limitación por defecto = `nombre` normalizado; el bloqueo adjunta
    `retry_after_seg=rate_limiter.segundos_restantes(clave)`.
- `guest(clave_limite: str) -> LoginResponseDTO`:
  - si hay rate limiter: `permitir(clave_limite)`; si bloqueado →
    `DemasiadosIntentosError(..., usuario="invitado",
    retry_after_seg=segundos_restantes(clave_limite))`; si no, `registrar_intento`.
  - token `generar("invitado", "invitado", expira_en, rol="invitado")`; `expira_en`
    con `PoliticaExpiracionService`. No usa `repo_usuarios`.

Sin DTO de request nuevo: `POST /api/auth/guest` no recibe body. Respuesta =
`LoginResponseDTO` (`{token, expira_en}`).

## 4. Adaptadores e Infraestructura

- `src/application/use_cases/autenticar_usuario.py` — `AutenticarUsuarioUseCase.guest(clave_limite) -> LoginResponseDTO`.
- `src/infrastructure/fastapi/error_handler.py` — `manejar_error_http`: si
  `code == 429` y `getattr(exc, "retry_after_seg", None)` es `int`, emite
  `HTTPException(429, detail, headers={"Retry-After": str(retry_after_seg)})`.
- `src/infrastructure/fastapi/routes/auth_router.py`:
  - helper `_fijar_cookie(response, settings, token)` (refactor del login).
  - `POST /guest`: `ip = request.client.host if request.client else "desconocida"`,
    `use_case.guest(clave_limite=f"ip:{ip}")`, fija cookie, evento
    `login_exitoso` con `usuario="invitado"`.

Sin cambios en `Settings` (reutiliza `LOGIN_*`).

## 5. Matriz de Pruebas (RED Suite)

### `tests/unit/test_guest_endpoint.py`

1. `test_guest_genera_token_sin_bd` — `guest("ip:1.2.3.4")` → token cuyos claims
   son `sub="invitado"`, `usuario="invitado"`, `rol="invitado"`, `exp` futuro.
2. `test_guest_handler_fija_cookie` — handler guest con `Response()` fija cookie
   `datamaq_token` HttpOnly/SameSite.
3. `test_me_con_token_guest` — `get_usuario_actual` decodifica token guest y
   `AutenticarUsuarioUseCase.me` devuelve `MeResponseDTO(usuario="invitado", rol="invitado")`.
4. `test_guest_rate_limit_por_ip` — 5 sesiones OK por IP; la 6ª →
   `DemasiadosIntentosError`; otra IP → OK.
5. `test_rate_limiter_segundos_restantes` — permitido → `0`; bloqueado → `1..ventana`.
6. `test_login_bloqueado_adjunta_retry_after` — login bloqueado → excepción con
   `retry_after_seg >= 1`.
7. `test_manejar_error_http_429_con_retry_after` — `manejar_error_http` con
   `retry_after_seg` → `HTTPException` 429 con header `Retry-After`.

### `tests/unit/test_observabilidad.py` (ajuste)

- `test_demasiados_intentos_con_usuario` (E7) — añadir `retry_after_seg=37` y
  assert del header `Retry-After == "37"`.

## 6. Criterios del Gauntlet

```bash
bash scripts/pre-push.sh   # integridad, ruff, pyright, tests unitarios >=85%
bash scripts/ci.sh         # + integración
```

`__init__.py` de 0 bytes. `domain/auth/` sin terceros. Cobertura del flujo guest,
rate limiter y Retry-After cubierta por la suite unitaria.
