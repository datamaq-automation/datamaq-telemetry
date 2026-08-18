# Contrato de Autenticación — datamaq-telemetry

> **Versión:** 1.2.0 · **Estado:** vigente · **Fuente de verdad:** `src/infrastructure/fastapi/routes/auth_router.py`, `src/infrastructure/settings/config.py`, `specs/auth.md`, `specs/auth-me.md`, `specs/usuario-invitado.md`, `specs/guest-endpoint.md`, `specs/roles-permisos.md`.

Contrato HTTP de autenticación para la SPA (`app-datamaq`). El frontend consume este contrato tal cual lo emite el backend; no se aplican workarounds en el cliente.

## Mecanismos de autenticación

- **Primario:** cookie `HttpOnly` (`datamaq_token`). No es legible por JavaScript.
- **Fallback (retrocompatibilidad):** header `Authorization: Bearer <token>`.
- El token es un JWT HS256 emitido **solo** por el backend. La SPA **nunca firma tokens**.
- Vigencia del token: `AUTH_TOKEN_EXPIRA_MINUTOS` minutos (default **120** en `Settings`, configurable); la cookie expira con `Max-Age = AUTH_TOKEN_EXPIRA_MINUTOS × 60`.

## POST /api/auth/login

### Request
```json
{ "usuario": "operador@planta.local", "contrasena": "secreto123" }
```

### Response 200
```json
{ "token": "<jwt>", "expira_en": "2026-08-17T12:00:00Z" }
```

Headers: `Set-Cookie: datamaq_token=<jwt>; HttpOnly; SameSite=strict; Max-Age=7200; Path=/` (con `Secure` en producción).

## POST /api/auth/logout

Borra la cookie de sesión (`Set-Cookie` con `Max-Age=0`). No requiere autenticación.

### Response 200
```json
{ "detail": "sesion_cerrada" }
```

## GET /api/auth/me

Restauración de sesión: devuelve `usuario` y `rol` leídos de los claims del JWT ya validado por el backend. La SPA lo usa al recargar para recuperar la identidad real (la cookie `HttpOnly` no es legible por JavaScript).

### Request

Sin body. Autenticación por cookie `datamaq_token` o header `Authorization: Bearer`.

### Response 200
```json
{ "usuario": "operador@planta.local", "rol": "operador" }
```

`rol` ∈ `{"admin", "operador", "invitado"}`. Si el claim `usuario` está ausente, se usa el fallback `sub`; si tampoco existe, `"anon"`.

### Response 401
```json
{ "detail": "credenciales_invalidas" }
```

Token ausente, inválido o con `rol` fuera del conjunto válido.

### Caso dev (`AUTH_REQUIRED=False`)

El backend cortocircuita la verificación y responde `200 {"usuario": "anon", "rol": "admin"}`.

## Acceso invitado

> **DEC-04:** el botón "Entrar como invitado" usa **`POST /api/auth/guest`** (público, sin body). Reemplaza a DEC-03 (que reutilizaba el login con credenciales del seed).

### POST /api/auth/guest

Emite un JWT `HS256` con claims `sub="invitado"`, `usuario="invitado"`, `rol="invitado"` **sin consultar la base de datos** y fija la cookie `datamaq_token`.

- **Request:** sin body.
- **Response 200:** igual que login:
```json
{ "token": "<jwt>", "expira_en": "2026-08-17T12:00:00Z" }
```
- **Rate limiting:** por IP (clave `ip:<host>`), reutilizando `LOGIN_MAX_INTENTOS` (5) y `LOGIN_VENTANA_SEGUNDOS` (300). Al excederse → `429` con cabecera `Retry-After`.
- **Permisos:** rol `invitado` = solo lectura (ver "Rutas protegidas"); las escrituras devuelven `403 forbidden`.

### Alternativa compatible (DEC-03 histórico)

El login estándar con el usuario fijo `invitado` sigue disponible para pruebas o scripts:

1. Seed manual (idempotente, no sobrescribe): `python scripts/seed_invitado.py`.
   - La contraseña se lee de la variable `GUEST_PASSWORD`; si no está definida, usa `invitado` emitiendo un warning a `stderr`.
2. `POST /api/auth/login` con `{"usuario": "invitado", "contrasena": "<GUEST_PASSWORD o 'invitado'>"}`.

## Errores

### Errores de dominio (vía `ErrorPresenter` → `detail` string)
| Código | `detail` | Caso |
|---|---|---|
| 401 | `credenciales_invalidas` | Credenciales incorrectas o token ausente/inválido |
| 403 | `usuario_inactivo` | Cuenta deshabilitada |
| 403 | `forbidden` | Sin rol `admin` en ruta protegida, o rol `invitado` en escritura |
| 422 | `El nombre de usuario no puede estar vacío.` | Usuario vacío tras normalizar |
| 429 | `Demasiados intentos...` | Rate limiting de login/guest (con cabecera `Retry-After: <segundos>`) |
| 404 | `{"detail": "Not Found"}` | Endpoint inexistente (p. ej. `/api/auth/guest`) — revisar este contrato, no inventar rutas |

### Errores de validación de request (FastAPI → `detail` array)
| Código | `detail` | Caso |
|---|---|---|
| 422 | array `[{type, loc, msg, input}]` | Cuerpo malformado o campos inválidos |

> **Decisión DEC-01:** el 422 de validación de request conserva el formato estándar de FastAPI (`detail` = array). No se reintroduce `detail` string tipo `cuerpo_invalido`. El frontend normaliza ambos formatos (string para errores de dominio, array para validación).

## Rutas protegidas

Sin cookie ni header válido → `401 {"detail": "credenciales_invalidas"}`.

Matriz por rol (DEC-04b): `invitado` = solo lectura; `admin`/`operador` = acceso completo.

| Endpoint | invitado | operador | admin |
|---|---|---|---|
| `GET /api/telemetria/{latest,instantaneous,energy}/*` | ✅ | ✅ | ✅ |
| `GET /api/dispositivos`, `GET /api/dispositivos/{id}` | ✅ | ✅ | ✅ |
| `POST /api/dispositivos`, `PUT /api/dispositivos/{id}` | ❌ 403 | ✅ | ✅ |
| `GET /api/organizaciones`, `GET /api/plantas` | ✅ | ✅ | ✅ |
| `POST /api/organizaciones`, `POST /api/plantas` | ❌ 403 | ✅ | ✅ |
| `GET /api/planes` | ✅ | ✅ | ✅ |
| `POST /api/planes` | ❌ 403 | ✅ | ✅ |
| `GET /api/alertas` | ✅ | ✅ | ✅ |
| `POST /api/alertas/{id}/resolver` | ❌ 403 | ✅ | ✅ |
| `POST /api/system/purge` | ❌ 403 | ❌ 403 | ✅ |
| `GET /api/auth/me` | ✅ | ✅ | ✅ |

Públicas: `POST /api/auth/login`, `POST /api/auth/guest`, `POST /api/auth/logout`, `GET /health`.

## WebSocket `/ws/live`

Autenticación por cookie `datamaq_token` (o header `Authorization: Bearer`) en el handshake. Sin token válido → cierre con código `1008`.

### WebSocket /ws/live — alcance

**Decisión DEC-02:** el stream es **global** para cualquier usuario autenticado. En esta iteración no se filtra por organización ni por rol; el filtrado multi-tenant es trabajo futuro que requiere el claim `organizacion_id` en el JWT.

## Migración SPA (Fase 2 — `app-datamaq`)

1. Dejar de leer `localStorage` (`datamaq.sesion`); la cookie viaja automáticamente en cada request.
2. Interceptor (`src/core/http/client.ts`): quitar inyección de `Authorization` (o mantener como fallback durante la migración).
3. Logout: llamar `POST /api/auth/logout` (borra la cookie `HttpOnly`, que JS no puede borrar).
4. Sesión expirada: depender de la respuesta `401` (la cookie `HttpOnly` no expone el claim `exp` a JavaScript).
5. Restauración de sesión al recargar: llamar `GET /api/auth/me` (reemplaza el sondeo/sessionStorage por la identidad real del JWT).
6. Acceso invitado: usar `POST /api/auth/guest` (ver sección "Acceso invitado"). No se envían credenciales.
