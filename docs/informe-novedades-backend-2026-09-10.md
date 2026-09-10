# Informe de Novedades — Backend (2026-09-10) y consulta al equipo Frontend

> **Para:** Equipo de Frontend (`app-datamaq` / `www-datamaq`)
> **De:** Equipo de Backend (`datamaq-telemetry`)
> **Fecha:** 2026-09-10
> **Tipo:** Informe de estado + pedido de sincronización. El backend agotó las tareas identificadas hasta ahora; no hay nada bloqueado de nuestro lado.

---

## 1. Resumen ejecutivo

Desde el último informe de contrato (telemetría), hubo dos frentes de trabajo nuevos:

1. **Cuentas de solo lectura y un rol nuevo** (`invitado_global`) — cambia el comportamiento de una cuenta que puede estar hardcodeada en el frontend.
2. **Grupos de dispositivos** — funcionalidad nueva completa: agrupar varios medidores de una misma planta (ej. dos trafos) y consultar el total sumado, tanto en vivo como histórico. Pensado originalmente para Durax, pero es un patrón general para cualquier cliente con más de un medidor por instalación.

Ambos están en producción, probados (unit + integración + smoke test manual contra el servidor real) y con CI/CD en verde.

---

## 2. Cuentas de solo lectura y rol `invitado_global`

*(Ya se envió un informe dedicado sobre esto — ver
`docs/informe-cambio-cuenta-invitado-y-rol-invitado-global.md`. Se resume
acá para que quede todo en un solo lugar.)*

- La cuenta `invitado@datamaq.com.ar` (preexistente, sin organización) fue reutilizada: ahora tiene organización asignada y ve un solo dispositivo. **Su contraseña cambió** — si está hardcodeada en algún lado del frontend, hay que actualizarla (pedirla a backend por canal seguro).
- Nuevo rol `invitado_global`: solo lectura, ve todos los dispositivos de todas las organizaciones. Agregarlo a cualquier tipo/switch de rol en el frontend, tratándolo igual que `invitado` (sin permisos de escritura).
- Se corrigió un bug de aislamiento: una cuenta sin organización asignada antes veía todos los dispositivos (bug), ahora ve `[]`. Si hay lógica de frontend que trata una lista vacía como error, revisarla — es una respuesta válida.

## 3. Grupos de dispositivos (funcionalidad nueva)

Caso de uso: una planta con más de un medidor (ej. un medidor por trafo) necesita ver el total sumado, no cada medidor por separado.

### Endpoints (`/api/v1/grupos-dispositivos`)

| Método | Ruta | Descripción | Permisos |
|---|---|---|---|
| `POST` | `` | Crea un grupo (`planta_id`, `nombre`, `dispositivos_ids[]`) | Cualquier rol excepto `invitado`/`invitado_global` |
| `GET` | `?planta_id=...` | Lista los grupos de una planta | Cualquier rol autenticado |
| `GET` | `/{grupo_id}` | Detalle de un grupo | Cualquier rol autenticado (404 si es de otra organización) |
| `PATCH` | `/{grupo_id}/miembros` | Agrega un dispositivo (`{"dispositivo_id": "..."}`) | Escritura |
| `DELETE` | `/{grupo_id}/miembros/{dispositivo_id}` | Quita un dispositivo | Escritura |
| `DELETE` | `/{grupo_id}` | Borra el grupo | Escritura |
| `GET` | `/{grupo_id}/resumen?granularity=day&dias=30&timezone=...` | Total **actual**: potencia instantánea sumada + energía acumulada sumada por período | Cualquier rol autenticado |
| `GET` | `/{grupo_id}/resumen/historico?hours=24&granularity=5m` | Serie de tiempo de potencia sumada (para graficar una curva de carga total) | Cualquier rol autenticado |

Reglas de negocio a tener en cuenta en la UI:
- Un dispositivo solo puede agregarse a un grupo de **su misma planta** (si no, el backend devuelve 422).
- Tope de 20 grupos por planta (422 si se supera — no está atado a ningún plan pago, es un tope de seguridad fijo).
- La suma tolera que los medidores no estén perfectamente sincronizados en el tiempo (cada uno tiene su propio reloj/cadencia) — es un comportamiento esperado, no un bug.
- `dispositivos_sin_dato` en las respuestas de `/resumen` y `/resumen/historico` lista qué dispositivos del grupo no tenían lectura todavía, para poder avisar en la UI que el total es parcial.
- `potencia_activa_total_w` puede venir `null` si **ningún** dispositivo del grupo tiene dato (distinto de `dispositivos_sin_dato` parcial).

### Tipos sugeridos para el frontend

```typescript
export interface GrupoDispositivos {
  id: string;
  planta_id: string;
  nombre: string;
  dispositivos_ids: string[];
  creado_en: string;
  actualizado_en: string;
}

export interface EnergiaAgregada {
  periodo: string; // fecha (día o primer día del mes según granularity)
  energia_activa_neta_kwh: number | null;
}

export interface ResumenGrupoDispositivos {
  grupo_id: string;
  potencia_activa_total_w: number | null;
  dispositivos_sin_dato: string[];
  energia_agregada: EnergiaAgregada[];
}

export interface PuntoPotenciaGrupo {
  momento: string; // ISO datetime, un bucket de la serie histórica
  potencia_activa_total_w: number | null;
  dispositivos_sin_dato: string[];
}
```

**No implementado a propósito (fuera de alcance actual):** nada más allá de lo de arriba — el histórico de potencia ya cubre el caso de "curva de carga total". Si aparece una necesidad nueva (ej. push en vivo del total por WebSocket en vez de polling), avisen y lo evaluamos.

---

## 4. Preguntas para el equipo de frontend

1. **¿Qué novedades tienen ustedes del lado frontend** que backend debería conocer (features en curso, cambios de UX que impliquen datos que hoy no exponemos, vistas nuevas planeadas)?
2. **¿Necesitan algún cambio o endpoint nuevo de backend** para lo que tienen planeado a corto plazo — en particular para consumir grupos de dispositivos (¿UI de alta/gestión de grupos? ¿dashboard con el total?) o la cuenta `invitado_global`?
3. **¿Ya recibieron y actualizaron** la contraseña nueva de `invitado@datamaq.com.ar` en donde esté hardcodeada?
4. Si van a graficar el histórico de potencia sumada (`/resumen/historico`), **¿qué `granularity`/`hours` esperan usar por defecto** para el gráfico? Puede ayudarnos a ajustar límites o caché si hace falta.

---
*Cualquier consulta sobre la integración o pruebas en el entorno de staging/producción puede canalizarse con el equipo de backend.*
