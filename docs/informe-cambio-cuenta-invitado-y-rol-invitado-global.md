# Informe de Cambio — Cuenta `invitado@datamaq.com.ar` y nuevo rol `invitado_global`

> **Para:** Equipo de Frontend (`app-datamaq` / `www-datamaq`)
> **De:** Equipo de Backend (`datamaq-telemetry`)
> **Fecha:** 2026-09-10
> **Tipo de cambio:** **Rompe compatibilidad** para quien tenga la cuenta `invitado@datamaq.com.ar` hardcodeada (credenciales o comportamiento esperado). Nuevo rol agregado, no rompe nada por sí solo.

---

## 1. Qué pasó

La cuenta `invitado@datamaq.com.ar` existía en producción desde el 2026-08-18 como
cuenta genérica de solo lectura, **sin organización asignada**. Hoy, al pedido de
scoping por organización, se la reutilizó y modificó:

1. **Se le asignó una organización** ("Hogar (medidor doméstico)") que solo contiene
   un dispositivo (`D48C49F03564`).
2. **Se le rotó la contraseña.** La contraseña anterior ya no es válida.

Si el frontend (código, `.env` de staging, demos, tests e2e, documentación interna)
tiene esta cuenta hardcodeada, **hay que actualizar la contraseña** y **esperar que
ahora vea un solo dispositivo en vez de todos**.

Además, de paso se corrigió un bug de aislamiento: antes, cualquier usuario sin
organización asignada veía **todos** los dispositivos de todas las organizaciones al
pegarle a `GET /api/v1/dispositivos` (el filtro trataba `organization_id = NULL` como
"sin filtro" en vez de "denegar todo"). Ahora es fail-closed: sin organización y sin
el nuevo rol de acceso global, la respuesta es una lista vacía `[]`. Esto afecta a
**cualquier** cuenta que tuviera rol `invitado`/`operador` sin organización asignada,
no solo a la de arriba.

## 2. Nuevo rol: `invitado_global`

Se agregó un cuarto rol de solo lectura para cubrir el caso "ver todos los medidores
de todas las organizaciones, sin poder modificar nada" (antes solo existía
`superadmin` para eso, que además tiene permisos de escritura). Se creó la cuenta
`estudiantes@datamaq.com.ar` con este rol nuevo.

```diff
- rol: Literal["superadmin", "admin", "operador", "invitado"]
+ rol: Literal["superadmin", "admin", "operador", "invitado", "invitado_global"]
```

Este campo aparece en:
- `POST /api/v1/auth/token` (respuesta `LoginResponseDTO`, campo `rol`)
- `POST /api/v1/auth/2fa/login` (ídem)
- `GET /api/v1/auth/me` (respuesta `MeResponseDTO`, campo `rol`, junto con
  `organizacion_id` y `organizacion_nombre`)

**Impacto en UI:** si el frontend tiene un `switch`/mapa de roles para mostrar
etiquetas, ocultar botones de edición, etc., agregar `"invitado_global"` a cualquier
lista donde ya esté `"invitado"`. Se comporta igual que `invitado` en todo lo
relevante para la UI:
- **No puede escribir nada** (crear/editar/borrar dispositivos, organizaciones,
  plantas, correcciones de cargas, etc. — bloqueado en el backend con `403`).
- **Sí puede leer** todo lo que expone la API en modo lectura.
- La única diferencia con `invitado` es el alcance: `invitado` ve solo los
  dispositivos de su organización asignada; `invitado_global` ve los de todas.

```typescript
// Sugerido: actualizar el tipo de rol en el frontend
export type Rol = "superadmin" | "admin" | "operador" | "invitado" | "invitado_global";

// Si existe una función tipo esSoloLectura(rol), agregar el nuevo valor:
export function esSoloLectura(rol: Rol): boolean {
  return rol === "invitado" || rol === "invitado_global";
}
```

## 3. Qué revisar en el frontend

1. **Buscar referencias hardcodeadas** a `invitado@datamaq.com.ar` (código, `.env`,
   fixtures de test, documentación) y actualizar la contraseña — pedirla al equipo de
   backend por un canal seguro, no va en este documento.
2. **No asumir que `GET /api/v1/dispositivos` devuelve la lista completa** para
   cuentas sin organización — ahora puede devolver `[]`. Si hay lógica que asume "si
   la lista está vacía, hubo un error", revisarla: una lista vacía es una respuesta
   válida (`200 OK`) para un usuario sin acceso a ningún dispositivo.
3. **Agregar `invitado_global`** a cualquier `switch`/enum/tipo de rol en el
   frontend, tratándolo igual que `invitado` para efectos de permisos de UI.
4. Si hay un demo o ambiente de pruebas que usaba `invitado@datamaq.com.ar` para
   mostrar "todos los medidores", ese caso de uso ahora lo cubre
   `estudiantes@datamaq.com.ar` (rol `invitado_global`) — pedir esa credencial si
   hace falta para demos.

---
*Cualquier consulta sobre la integración o pruebas en el entorno de staging/producción puede canalizarse con el equipo de backend.*
