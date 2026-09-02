# Manejo de rechazo de autenticación en WebSocket `/ws/live`

## 1. Objetivo y Contexto

Fase 3 del plan de inmediatez (pendiente en `specs/inmediatez-telemetria-en-vivo.md`:
"manejo de 403 del WS").

Hoy, con `AUTH_REQUIRED=true` y token inválido, el endpoint `/ws/live` ejecuta
`await websocket.close(code=1008)` **antes** de `websocket.accept()`. Un navegador real no
puede leer ese código: el handshake se rechaza a nivel HTTP y el cliente JS solo observa
`onclose` con código 1006, indistinguible de una caída de red. La SPA entra en reintentos
infinitos sin poder redirigir a login.

**Alcance:** aceptar primero el socket y, si el token es inválido, cerrar con un código de
aplicación explícito `4401` que el cliente pueda distinguir de otros fallos.

**Fuera de alcance:** el manejo del cierre en la SPA (fase de frontend), la renovación de
token y cualquier cambio en la validación JWT en sí (`token_valido` no se modifica).

## 2. Dominio & Puertos

Sin cambios en `domain/` ni `application/`. Cambio exclusivo de Infrastructure
(`src/infrastructure/fastapi/server.py`). No se crean puertos, entidades ni DTOs.

## 3. Caso de uso & DTOs

Endpoint WebSocket `/ws/live`:

1. Siempre `await websocket.accept()`.
2. Si `settings.AUTH_REQUIRED` y `token_valido(...)` es falso:
   - `await websocket.close(code=4401, reason="token_invalido")`
   - `return` (sin registrar el socket en `active_websockets`).
3. Si la autenticación es válida (o no requerida), registrar y entrar al loop de lectura.

Contrato: constante `WS_CLOSE_TOKEN_INVALIDO = 4401` a nivel de módulo.

## 4. Matriz de Pruebas (RED Suite)

- `test_ws_cierra_con_4401_si_token_invalido`
  Dado `AUTH_REQUIRED=true` y sin token/cookie
  Cuando el cliente se conecta a `/ws/live`
  Entonces la conexión se acepta y se cierra con código `4401` (razón `token_invalido`).

- `test_ws_acepta_token_valido_y_permanece_abierto`
  Dado `AUTH_REQUIRED=true` y cookie `datamaq_token` con JWT válido
  Cuando el cliente se conecta y envía un mensaje
  Entonces no hay cierre (sin `WebSocketDisconnect`) y la sesión queda abierta.

## 5. Criterios del Gauntlet

- `ruff check .` y `ruff format --check .` sin errores.
- `pyright` en modo strict sin diagnósticos.
- `pytest --cov=src --cov-fail-under=85` en verde.
- `./scripts/pre-push.sh` (etapas 1-4) exitoso.
