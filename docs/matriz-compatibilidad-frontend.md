# Matriz de compatibilidad frontend-backend (transitoria)

> Versionada en este repo. Se verifica con `git grep` cada vez que cambia el contrato.
> Fuentes: `decisions/2026-10-24_compatibilidad-frontend-backend-en-deploy.md`,
> `decisions/2026-10-25_compatibilidad-invitado-hasta-main-frontend.md` y
> `decisions/2026-10-29_contrato-dos-versiones-expansion.md` (repo padre `datamaq`).

## Qué mide esta matriz

Hay dos backends (`main` y `develop` de `datamaq-telemetry`) y dos frontends (`main` y `develop` de
`app-datamaq`). Cada fila es una llamada que hace el frontend y muestra si la ruta existe en cada backend,
y qué frontend la llama. La compatibilidad transitoria en `develop` (opción A, 2026-10-29) existe para que
`develop` del backend atienda a los dos frontends mientras dura la transición.

Regla de la decisión: **expansión antes de contracción.** No se quita un endpoint del backend hasta confirmar
que `develop` del frontend ya no lo llama.

## Matriz

Verificación de existencia en el backend (`git grep` sobre `origin/main` y `origin/develop`, carpeta `src/`).
"Frontend que la llama" viene de las decisiones citadas arriba.

| # | Llamada del frontend | Backend `main` | Backend `develop` | Llamada por `main` del frontend | Llamada por `develop` del frontend | Estado |
|---|---|---|---|---|---|---|
| 1 | `POST /api/v1/auth/guest` (botón de invitado, `/demo`, `?guest=true`) | no existe | no existe (no se restaura, opción A) | sí (`src/core/services/auth.ts:41`) | no | **Roto.** Responde 404 en `app-dev` y en prod. No es compatibilidad: no se restaura. |
| 2 | `GET /api/v1/auth/me` y `/api/v1/auth/2fa/*` con rol `invitado` o `invitado_global` | sí (compat PR #76) | sí (compat PR #76) | sí | no (el schema de `develop` rechaza esos roles) | **Compatible.** Se quita con la condición de cierre (abajo). |
| 3 | `GET /api/v1/oauth/consent-info` con planta `null` | sí | sí | sí | sí | **Compatible.** `main` muestra "Planta Principal" (texto engañoso, corregido en `develop`). |
| 4 | Telemetría, cargas, máquinas, facturas, copilot, planes, suscripciones, WebSocket | mismo contrato | mismo contrato | sí | sí | **Compatible.** Sin cambio de contrato. |
| 5 | `GET/POST /api/v1/integraciones/mcp/token[/regenerar]` | no existe | no existe | sí (`src/core/services/integracionesService.ts:18,34`) | no | **Roto en prod.** No es compatibilidad: lo resuelve el release de `develop` del frontend (OAuth). |
| 6 | `/api/v1/oauth/aplicaciones-conectadas` (listado y revocación por `client_id`) | no existe | no existe | sí (`integracionesService.ts:50,69`) | no (usa `/api/v1/usuarios/integraciones`) | **Roto en prod.** Lo resuelve el release de `develop` del frontend. |
| 7 | `GET /api/v1/usuarios/integraciones` | sí (`oauth_router.py`) | sí (`oauth_router.py`) | no | sí | **Compatible.** Ruta que usa `develop` del frontend en lugar de la fila 5-6. |
| 8 | Notificador Tuya | sí solo con prefijo `/api/v1/tuya/notificador/estado` (`notificador_router.py:22`) | sí, mismo prefijo | sí, **sin prefijo** (`src/core/services/tuya.service.ts:5`) | sí, con prefijo | **Roto en prod** para `main` del frontend. `develop` del frontend ya llama la ruta correcta. |
| 9 | Documentación SGE, campo `rolesPermitidos` (contrato de respuesta, no es una ruta) | responde `admin` | responde `admin` | espera `administrador` y descarta el catálogo (#44) | corregido | **Roto en prod** para `main` del frontend. Corregido en `develop` del frontend. |

Filas 5, 6, 8 y 9: no dependen de la compatibilidad de invitado. Se resuelven cuando `develop` del frontend
llega a `main` (release, #70 de `app-datamaq`). No se les aplica la condición de cierre de abajo.

## Condición de cierre de la compatibilidad de `invitado` e `invitado_global`

La compatibilidad de las filas 2 se quita **cuando `main` de `app-datamaq` deje de llamar a esos roles y a la
ruta de la fila 1**. No se usa una fecha. Comprobación (en `app-datamaq`, sobre `origin/main`):

```bash
git grep -n -e invitado -e invitado_global -e auth/guest origin/main -- src tests
```

La condición se cumple cuando el comando no devuelve resultados. Recién entonces se quitan en este repo:

- `src/infrastructure/fastapi/compat_roles_invitado.py` (roles de compatibilidad).
- El uso de esos roles en `src/infrastructure/fastapi/routes/auth_router.py` y en
  `src/infrastructure/fastapi/dependencies.py` (chequeo de 2FA y `/me`).

Antes de quitar cualquier ruta de la matriz, verificar que `develop` del frontend ya no la llama (regla de
expansión antes de contracción).

## Estado al 2026-10-29

Medido con las referencias locales de `app-datamaq` (sin `fetch`). **La condición de cierre no se cumple:**
`git grep -e invitado -e invitado_global -e auth/guest origin/main -- src tests` devuelve 76 líneas (por
ejemplo, `src/core/services/auth.ts:41` llama `POST /api/v1/auth/guest`, y `src/core/schemas/auth.ts:27-28`
define los roles). `develop` del frontend no tiene `auth/guest` y solo conserva `invitado` en el schema y en
los tests.

Esta sección es una foto del día. La fuente de verdad es el `git grep` de arriba, que se repite antes de
cada cambio de contrato.
