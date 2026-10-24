# Spec — CORS y cookies para `app-dev.datamaq.com.ar`

> Borrador para aprobación del padre (`datamaq-da`). **Solo spec: sin código, sin push.**
> Untracked. Complementa `spec-api-dev.md` (backend en `api-dev`). Producción no cambia.

## 1. Objetivo y contexto

El frontend de dev (`https://app-dev.datamaq.com.ar`) llama al backend de dev (`https://api-dev.datamaq.com.ar`) con
credenciales (cookie `datamaq_token`). Hace falta:
1. Permitir ese origen en CORS **con credenciales**, sin comodín.
2. Confirmar que la cookie de sesión viaja entre los dos subdominios.
3. Permitir ese origen en el WebSocket `/ws/live`.
4. Probarlo, y probar que producción no cambia.

## 2. Estado verificado (código, esta sesión)

**CORS**
- Config: `CORS_ORIGINS` (`src/infrastructure/settings/config.py:64`). Default: `""` en producción, `http://localhost:5173` en el resto (`config.py:144-145`).
- Montaje: `src/infrastructure/fastapi/server.py:475-493`. Lista = `CORS_ORIGINS` (separado por comas) **más** los orígenes fijos de Cybersyn (`auth_cookies.py:15-19`). `allow_credentials=True` salvo que sea `"*"`.
- `"*"` se rechaza fuera de DEBUG (`server.py:477-478`, `config.py:161-162`).
- **Conclusión:** el origen de dev se agrega **solo por variable de entorno**: `CORS_ORIGINS=https://app-dev.datamaq.com.ar`. No hace falta cambiar código para CORS.

**Cookie `datamaq_token`**
- Nombre: `config.py:58` (`AUTH_COOKIE_NOMBRE`).
- `HttpOnly`: `config.py:59` (`AUTH_COOKIE_HTTPONLY = True`).
- `SameSite`: `config.py:60`, default **`strict`**. Para orígenes Cybersyn: `none` (`auth_cookies.py:49-56`).
- `Secure`: `config.py:188`, `auth_cookie_secure = not DEBUG`. **Depende de DEBUG, no de una variable propia.**
- `Domain`: **no se fija en ningún lado** (`auth_cookies.py:67-75`, `eliminar_cookie_auth` en 99-107). La cookie es *host-only* (solo `api-dev.datamaq.com.ar`).
- `Path`: default `/` en la cookie de sesión. La de dispositivo confiable usa `/api/v1/auth`.

**WebSocket `/ws/live`**
- `server.py:512-516`: acepta la conexión **antes** de validar nada.
- `_autenticar_cliente_ws` (`server.py:389-409`): toma el token de la **cookie** (ambiente) o del header `Authorization`. **No valida `Origin`.**
- `CORSMiddleware` de Starlette **no aplica a WebSockets**: la lista de CORS no protege `/ws/live`.

## 3. Análisis de sitio (same-site)

- `app-dev.datamaq.com.ar` y `api-dev.datamaq.com.ar` son **same-site** (mismo eTLD+1 `datamaq.com.ar`, mismo esquema). Por eso `SameSite=strict` **sí** envía la cookie en `fetch` con credenciales desde app-dev. *Verificar con la lista de sufijos públicos antes de cerrar.*
- Sin `Domain`, la cookie queda atada a `api-dev`; app-dev nunca la lee directamente (es HttpOnly), y no la necesita.
- **Riesgo WebSocket (CSWSH):** `SameSite=strict` no se envía en handshakes *cross-site*, pero **sí** se envía desde cualquier origen *same-site* (otro subdominio de `datamaq.com.ar`) y desde Cybersyn (`SameSite=None`). Sin validación de `Origin`, una página de un origen permitido puede abrir `/ws/live` con la cookie de la víctima y leer el stream de telemetría. **Este es el hallazgo principal de esta spec.**

## 4. Decisiones

**C1 — Origen de dev en CORS:** solo variable de entorno `CORS_ORIGINS=https://app-dev.datamaq.com.ar` en el `.env` de dev. Sin cambio de código. Producción sigue con su `CORS_ORIGINS` actual (sin dev).

**C2 — Atributo `Domain`:** el dueño lo pidió. **Propuesta: no fijar `Domain`.** Una cookie host-only es más estricta: no se comparte con otros subdominios. Como app-dev no lee la cookie y la petición es same-site, no hace falta. Si el dueño insiste, hay que agregar `COOKIE_DOMAIN` (setting nuevo) y su test. **Requiere OK.**

**C3 — `Secure` en dev:** el valor sale de `DEBUG`. Opciones: (a) dev con `DEBUG=false` (recomendado en `spec-api-dev.md` D3), o (b) agregar `AUTH_COOKIE_SECURE` como override explícito. Recomendado (a): no requiere código.

**C4 — Origen del WebSocket (cambio de código, requiere OK):**
- Validar `websocket.headers["origin"]` contra la **misma** lista que CORS (`CORS_ORIGINS` + Cybersyn), antes de `accept()`.
- Si el origen falta o no está en la lista: cerrar con código `1008` (policy violation) y loguear `ws_origen_rechazado`.
- **Modo de fallo:** fail-closed. Justificación: es el mismo criterio que #23 (decidido por el dueño). Un origen desconocido no debe recibir telemetría.
- Compatibilidad: los clientes que no mandan `Origin` (scripts, MCP) **no** son navegadores. Propuesta: rechazarlos también cuando `AUTH_REQUIRED=true`, o aceptar solo con token por `Authorization`. *Decidir antes de implementar; afecta a integraciones existentes.*

**C5 — Comodín:** no se usa `"*"` en ningún entorno con credenciales (ya lo impide `server.py:477`). La prueba lo fija.

## 5. Diseño de cambio mínimo

| Archivo | Cambio | Necesita OK |
|---|---|---|
| `.env` de dev (en el VPS, dueño) | `CORS_ORIGINS=https://app-dev.datamaq.com.ar`, `DEBUG=false` | Sí (dueño, VPS) |
| `src/infrastructure/fastapi/server.py` | Validación de `Origin` en `websocket_stream` antes de `accept()` (C4) | Sí (padre) |
| `src/infrastructure/fastapi/origenes.py` (nuevo, opcional) | Función única `origen_permitido(origin, settings)` usada por CORS y WS, para no duplicar la lista | Sí si se crea |
| `tests/unit/test_cors_app_dev.py` (nuevo) | Pruebas de §6 | No (es test) |

## 6. Pruebas (TestClient, mismo patrón que `tests/unit/test_cors_cybersyn.py`)

| # | Prueba | Esperado |
|---|---|---|
| T1 | Preflight `OPTIONS` con `Origin: https://app-dev.datamaq.com.ar`, con `CORS_ORIGINS` de dev | `access-control-allow-origin` = ese origen; `access-control-allow-credentials: true` |
| T2 | Mismo preflight con `CORS_ORIGINS` de producción (sin dev) | Sin `access-control-allow-origin` para app-dev |
| T3 | Origen `https://app.datamaq.com.ar` (prod) con config de dev | Sin allow (dev no abre prod) |
| T4 | Origen Cybersyn (`https://cybersyn.com.ar`) sigue permitido | Como hoy (regresión) |
| T5 | `CORS_ORIGINS="*"` fuera de DEBUG | `ValueError` al crear settings (ya existe; se mantiene) |
| T6 | Login desde app-dev: cookie `datamaq_token` con `HttpOnly`, `SameSite=Strict`, sin `Domain`; `Secure` según DEBUG | Atributos exactos en `set-cookie` |
| T7 | `/ws/live` con `Origin` de app-dev y cookie válida | Conexión aceptada (C4) |
| T8 | `/ws/live` con `Origin: https://evil.example` | Cierre `1008`, sin datos (C4) |
| T9 | `/ws/live` sin `Origin` | Según decisión C4 (rechazo o aceptación con `Authorization`) |
| T10 | Config de producción: el default de `CORS_ORIGINS` sigue `""` | Regresión sobre `config.py:144` |

Los tests T7–T9 solo se escriben si C4 se aprueba. T1–T6 y T10 no cambian código de producción.

## 7. Criterios de aceptación

- app-dev hace `fetch` con credenciales a api-dev y recibe respuesta autenticada.
- `/ws/live` rechaza orígenes no listados (si C4 se aprueba).
- Producción: mismo `CORS_ORIGINS`, mismas cookies, mismo comportamiento (T2, T10 en verde).
- Gauntlet local `APP_ENV=test ./scripts/pre-push.sh` en verde, redirigido a archivo.

## 8. Qué no se hace

- No se usa `"*"` ni se abre CORS para otros dominios.
- No se cambia la política de cookies de Cybersyn (`SameSite=None; Secure`).
- No se toca el VPS: el `.env` de dev lo edita el dueño.
- No hay push ni PR; no se toma código hasta el OK del padre.

## 9. Preguntas para el dueño (vía padre)

1. **C2:** ¿mantenemos la cookie host-only (sin `Domain`, recomendado) o querés `Domain`? Si es `Domain`, ¿`.datamaq.com.ar`?
2. **C4:** ¿aprobás validar `Origin` en `/ws/live` (fail-closed)?
3. **C4 (sin Origin):** ¿un cliente sin `Origin` (script, MCP) debe seguir funcionando, o solo con `Authorization`?
4. **C3:** ¿dev con `DEBUG=false` (cookie `Secure`) o un override `AUTH_COOKIE_SECURE`?

## 10. Hallazgo para el padre (fuera de alcance de dev)

`/ws/live` acepta cualquier `Origin` con la cookie de sesión. Aunque el riesgo es mayor con la cookie `SameSite=None` de Cybersyn, aplica también hoy en producción. **Recomendación:** tratar C4 como fix de producción, no solo de dev, y priorizarlo.
