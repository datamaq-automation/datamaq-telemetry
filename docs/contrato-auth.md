# Contrato de Autenticación — datamaq-telemetry

Contrato HTTP de autenticación para la SPA (`app-datamaq`). El frontend consume este contrato tal cual lo emite el backend; no se aplican workarounds en el cliente.

## Mecanismos de autenticación

- **Primario:** cookie `HttpOnly` (`datamaq_token`). No es legible por JavaScript.
- **Fallback (retrocompatibilidad):** header `Authorization: Bearer <token>`.
- El token es un JWT HS256 emitido **solo** por el backend. La SPA **nunca firma tokens**.
- Vigencia del token: 480 minutos (`AUTH_TOKEN_EXPIRA_MINUTOS`); la cookie expira con el mismo `Max-Age`.

## POST /api/auth/login

### Request
```json
{ "usuario": "operador@planta.local", "contrasena": "secreto123" }
```

### Response 200
```json
{ "token": "<jwt>", "expira_en": "2026-08-17T12:00:00Z" }
```

Headers: `Set-Cookie: datamaq_token=<jwt>; HttpOnly; SameSite=strict; Max-Age=28800; Path=/` (con `Secure` en producción).

## POST /api/auth/logout

Borra la cookie de sesión (`Set-Cookie` con `Max-Age=0`).

### Response 200
```json
{ "detail": "sesion_cerrada" }
```

## Errores

### Errores de dominio (vía `ErrorPresenter` → `detail` string)
| Código | `detail` | Caso |
|---|---|---|
| 401 | `credenciales_invalidas` | Credenciales incorrectas o token ausente/inválido |
| 403 | `usuario_inactivo` | Cuenta deshabilitada |
| 403 | `forbidden` | Sin rol `admin` en ruta protegida |
| 422 | `El nombre de usuario no puede estar vacío.` | Usuario vacío tras normalizar |
| 429 | `Demasiados intentos...` | Rate limiting de login |

### Errores de validación de request (FastAPI → `detail` array)
| Código | `detail` | Caso |
|---|---|---|
| 422 | array `[{type, loc, msg, input}]` | Cuerpo malformado o campos inválidos |

> **Decisión DEC-01:** el 422 de validación de request conserva el formato estándar de FastAPI (`detail` = array). No se reintroduce `detail` string tipo `cuerpo_invalido`. El frontend normaliza ambos formatos (string para errores de dominio, array para validación).

## Rutas protegidas

Sin cookie ni header válido → `401 {"detail": "credenciales_invalidas"}`.

- Telemetría: `GET /api/telemetria/{latest,instantaneous,energy}/*`
- Dispositivos: `GET /api/dispositivos`, `GET /api/dispositivos/{id}`, `POST`, `PUT`
- Organizaciones y plantas: `GET/POST /api/organizaciones`, `GET/POST /api/plantas`
- Planes: `GET/POST /api/planes`
- Alertas: `GET /api/alertas`, `POST /api/alertas/{id}/resolver`
- Sistema: `POST /api/system/purge` (requiere rol `admin`)

Públicas: `POST /api/auth/login`, `POST /api/auth/logout`, `GET /health`.

## WebSocket `/ws/live`

Autenticación por cookie `datamaq_token` (o header `Authorization: Bearer`) en el handshake. Sin token válido → cierre con código `1008`.

## Migración SPA (Fase 2 — `app-datamaq`)

1. Dejar de leer `localStorage` (`datamaq.sesion`); la cookie viaja automáticamente en cada request.
2. Interceptor (`src/core/http/client.ts`): quitar inyección de `Authorization` (o mantener como fallback durante la migración).
3. Logout: llamar `POST /api/auth/logout` (borra la cookie `HttpOnly`, que JS no puede borrar).
4. Sesión expirada: depender de la respuesta `401` (la cookie `HttpOnly` no expone el claim `exp` a JavaScript).
