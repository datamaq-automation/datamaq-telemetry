# Informe de Cambios en el Contrato de Telemetría

> **De:** equipo backend (`datamaq-telemetry`) · **Para:** equipo frontend (`app-datamaq`)
> **Fecha:** 2026-09-01 · **Estado:** implementado en backend, **pendiente de ajuste en la SPA**

Este documento describe los cambios de contrato de la API de telemetría, qué los motivó y
qué hay que tocar del lado de la SPA. **Hay cambios rompientes**: se listan primero.

> [!IMPORTANT]
> OpenAPI está deshabilitado en producción (`API_EXPOSE_DOCS`): `/docs`, `/redoc` y
> `/openapi.json` devuelven 404. Este documento es la fuente de verdad del contrato.

---

## 1. Resumen ejecutivo

| # | Cambio | ¿Rompe? | Acción en la SPA |
|---|---|---|---|
| 1 | Timestamps con offset (`...Z`) | No | Ninguna. Se corrige solo un error de 3 h |
| 2 | `estado_fp` / `estado_tension` admiten `SIN_DATOS` | **Sí** | Ampliar el enum de Zod |
| 3 | `net_apparent_power_VA` y `power_factor` dejan de ser `null` | No | Revisar fallbacks tipo `?? '—'` |
| 4 | `desbalance_corriente_porcentaje` pasa a `null` con carga baja | Posible | Revisar `.toFixed()` directo |
| 5 | La potencia aparente cambia de fórmula (`hypot(P,Q)` → `V·I`) | No | Los históricos cambian de valor |
| 6 | La compensación de reactiva exige 500 W | No | Menos recomendaciones, más honestas |

---

## 2. Cambio rompiente: `estado_fp` y `estado_tension` admiten `SIN_DATOS`

### Qué pasaba

La API devolvía esto para el medidor real, y el dashboard lo mostraba fielmente:

```json
"factor_potencia_total": null,
"analitica": { "estado_fp": "OPTIMO" }
```

Un badge **«ÓPTIMO»** al lado de un guion. `determinar_estado_fp(None)` devolvía `OPTIMO`,
y tanto el value object como el DTO repetían ese default. Lo mismo con `estado_tension`,
que devolvía `NORMAL` sin ninguna tensión medida: un medidor caído reportando "tensión normal".

### Qué cambia

Ambos enums ganan el valor `SIN_DATOS`, que es lo que se devuelve cuando no hay medición:

```
EstadoFactorPotencia: OPTIMO | ADVERTENCIA | PENALIZADO | SIN_DATOS
EstadoTension:        NORMAL | SUBTENSION  | SOBRETENSION | SIN_DATOS
```

El DTO además pasa a tipar con el enum del dominio en vez de `str` sin validar.

### Por qué rompe la SPA

`app-datamaq/src/core/schemas/telemetria.ts:5` declara un enum cerrado:

```typescript
export const EstadoFactorPotenciaSchema = z.enum(['OPTIMO', 'ADVERTENCIA', 'PENALIZADO'])
```

y `app-datamaq/src/core/services/telemetry.ts:55` lo consume con **`.parse()`, no
`.safeParse()`**. Ante `"SIN_DATOS"` Zod **lanza**, y la tarjeta de última lectura no
degrada: deja de renderizar.

### Qué hacer

1. Ampliar ambos enums en `src/core/schemas/telemetria.ts:5-6`.
2. Cubrir el caso nuevo en el `switch` de `src/features/telemetria/components/LatestReadingCard.vue:34-40`.
   Sugerencia: estado neutro (gris), no verde ni rojo — es ausencia de dato, no un veredicto.
3. **Recomendado, más allá de este cambio:** pasar `telemetry.ts:55` de `.parse()` a
   `.safeParse()`. Hoy cualquier valor que el backend agregue a cualquier enum tumba la
   pantalla entera en vez de degradar. Es una fragilidad estructural del contrato.

---

## 3. Timestamps: ahora con zona horaria explícita

### Qué pasaba

```json
"registrado_en": "2026-09-01T23:20:00"
```

Sin offset. El valor era UTC, pero **JavaScript interpreta ese formato como hora local**.
Una medición tomada a las **20:20** se mostraba como **11:20**: tres horas de corrimiento,
exactamente el offset de Argentina. Afectaba a los 17 campos datetime de la API.

La guía de integración ya declaraba `registrado_en: string; // ISO 8601 UTC`, así que el
contrato documentado y la implementación no coincidían.

### Qué cambia

```json
"registrado_en": "2026-09-01T23:20:00Z"
```

No hace falta ningún cambio en la SPA: `registrado_en` sigue siendo `z.string()` y
`new Date(...)` ahora parsea el instante correcto.

> [!WARNING]
> **Se va a percibir como una regresión y no lo es.** Las lecturas van a aparecer "tres horas
> antes" de lo que la gente está acostumbrada a ver. Lo que se veía antes estaba mal.

Si la SPA tiene alguna compensación horaria propia para corregir este desfase, **hay que
quitarla**, o el error se duplica.

Esto además unifica REST con el WebSocket, que emitían formatos distintos para el mismo campo.

---

## 4. Potencia aparente y factor de potencia: ahora vienen con valor

### Qué pasaba

El firmware publica el formato compacto `{"n":"R","v":227.7,"i":0.9,"p":147,"q":-51}`, **sin
potencia aparente**. La ingesta no la derivaba, así que `net_apparent_power_VA` y
`power_factor` llegaban en `null` en `/latest` y en `granularity=raw`.

Peor: el path de agregación **sí** la derivaba, pero con `hypot(P,Q)`. O sea que la misma API
devolvía `null` en `raw` y un número en las granularidades agregadas, calculado con otra
definición.

### Qué cambia

Se unifica en **`S = V_rms · I_rms`**, la definición exacta de potencia aparente y lo que mide
una pinza. A diferencia de `hypot(P,Q)`, incluye la potencia de distorsión, que en cargas
conmutadas es sustancial:

| Fase R del medidor real | `hypot(P,Q)` | `V·I` |
|---|---|---|
| V=227.7, I=0.9, P=147, Q=-51 | S=155.6 → **FP 0.94** | S=204.93 → **FP 0.72** |

La brecha es potencia de distorsión, que antes quedaba invisible.

**Consecuencia:** los históricos agregados cambian de valor. `V·I ≥ hypot(P,Q)` siempre que
haya distorsión, así que **S sube y FP baja** en los gráficos de tendencia. Se ejecutó una
migración de backfill que recalcula el histórico, de modo que no debería quedar un escalón en
la fecha de despliegue.

---

## 5. Indicadores que ahora se abstienen

Dos indicadores devolvían números que no describían nada bajo carga despreciable:

**`desbalance_corriente_porcentaje`** devolvía `170.0` con la fase R en 0.9 A y las otras dos
en miliamperes. Ahora exige **5 A de corriente promedio** y devuelve `null` por debajo: sin
carga el desbalance no es "0%", es no medible. El umbral sigue el precedente que ya usaba la
detección de TI invertido.

**El dimensionamiento de compensación** llegaba a recomendar un banco de 2.5 kVAr y estimar
una penalización de **ARS 4.774** sobre una carga de 148 W en standby. Ahora exige **500 W** de
potencia activa —el mismo umbral que ya aplicaba la alerta de bajo factor de potencia— antes de
devolver `potencia_reactiva_a_compensar_kvar`, `banco_sugerido_kvar` o
`penalizacion_estimada_ars`. El `estado_fp` se sigue reportando: la medición es real, lo que no
corresponde es dimensionar nada sobre ella.

Ambos campos ya estaban declarados `number | null` en el contrato, así que esto no rompe el
tipado; sí conviene revisar cualquier `.toFixed()` o formateo que asuma número.

---

## 6. Antes y después, con datos reales

Medidor `D48C49F03564`, lectura del `2026-09-01 23:20 UTC`.

**Antes:**

```json
{
  "registrado_en": "2026-09-01T23:20:00",
  "fase_r": { "voltage_V": 227.7, "current_A": 0.9, "net_active_power_W": 147.0,
              "net_apparent_power_VA": null, "power_factor": null },
  "potencia_aparente_total_VA": null,
  "factor_potencia_total": null,
  "analitica": {
    "requiere_compensacion": false,
    "desbalance_corriente_porcentaje": 170.0,
    "estado_fp": "OPTIMO"
  }
}
```

**Después:**

```json
{
  "registrado_en": "2026-09-01T23:20:00Z",
  "fase_r": { "voltage_V": 227.7, "current_A": 0.9, "net_active_power_W": 147.0,
              "net_apparent_power_VA": 204.93, "power_factor": 0.72 },
  "potencia_aparente_total_VA": 227.78,
  "factor_potencia_total": 0.65,
  "analitica": {
    "requiere_compensacion": false,
    "potencia_reactiva_a_compensar_kvar": null,
    "banco_sugerido_kvar": null,
    "penalizacion_estimada_ars": null,
    "desbalance_tension_porcentaje": 0.28,
    "desbalance_corriente_porcentaje": null,
    "estado_fp": "PENALIZADO",
    "estado_tension": "NORMAL"
  }
}
```

El `estado_fp` pasa de `OPTIMO` a `PENALIZADO` porque ahora hay un factor de potencia medido
(0.65) y está por debajo del umbral de 0.95. Es la misma instalación: lo que cambió es que
antes no se medía y se afirmaba que estaba bien.

---

## 7. Contratos TypeScript actualizados

Reemplazan a los de [`docs/frontend-integration-guide.md`](./frontend-integration-guide.md) §4.1:

```typescript
export type EstadoFactorPotencia = 'OPTIMO' | 'ADVERTENCIA' | 'PENALIZADO' | 'SIN_DATOS';
export type EstadoTension = 'NORMAL' | 'SUBTENSION' | 'SOBRETENSION' | 'SIN_DATOS';

export interface AnaliticaCalidadEnergiaDTO {
  requiere_compensacion: boolean;
  // Los tres siguientes son null si la potencia activa es menor a 500 W
  potencia_reactiva_a_compensar_kvar: number | null;
  banco_sugerido_kvar: number | null;
  penalizacion_estimada_ars: number | null;

  desbalance_tension_porcentaje: number | null;
  desbalance_corriente_porcentaje: number | null; // null si la corriente promedio < 5 A

  estado_fp: EstadoFactorPotencia;
  estado_tension: EstadoTension;
}

export interface MedicionFaseDTO {
  voltage_V: number | null;
  current_A: number | null;
  net_active_power_W: number | null;
  net_reactive_power_VAR: number | null;
  net_apparent_power_VA: number | null;  // S = V·I; null solo si falta V o I
  power_factor: number | null;           // FP = P/S en [-1, 1]; null si S <= 0
  thd_v_pct?: number | null;
  thd_i_pct?: number | null;
}
```

El resto de `LecturaInstantaneaDTO` no cambia de forma; sí cambia el formato de
`registrado_en`, que ahora siempre termina en `Z`.

---

## 8. Deuda de contrato pendiente

Detectada durante esta revisión, **sin resolver todavía**. Se listan porque afectan al
consumo desde la SPA y conviene decidirlas juntos.

1. **`analitica` viene duplicada** en `/api/telemetria/latest/{id}`: aparece en
   `instantanea.analitica` y también en el nivel raíz `analitica`, con contenido idéntico.
   Hay que elegir cuál es canónica y deprecar la otra. Por ahora se siguen emitiendo las dos.

2. **El WebSocket y REST no hablan el mismo idioma.** Para el tópico `.../inst`, el canal en
   vivo publica el **payload crudo del firmware** (claves compactas `f`, `n`, `v`, `i`, `p`,
   `q`), mientras REST devuelve el DTO normalizado (`voltage_V`, `net_active_power_W`,
   `analitica`, …). La SPA necesita dos parsers para el mismo dato, y el canal en vivo nunca
   recibe potencia aparente, factor de potencia ni analítica — justamente lo que arregla este
   trabajo. Los tópicos de alertas sí publican el DTO; `inst` debería hacer lo mismo.

3. **Enums sin validar en otros DTOs**, mismo defecto que tenía `estado_fp`: `severidad` en
   `AlertaResponseDTO`, `estado` y `tipo_instalacion` en `DispositivoResponseDTO`, `modo_free`
   en `OrganizacionResponseDTO`, `tipo` en `NodoUnifilarDTO`. Todos declarados `str`.

4. **`fases_con_ti` es un CSV dentro de un string** (`"R,S,T"`) en vez de una lista tipada.

5. **Un payload monofásico se replica en las tres fases.** Si el mensaje no trae la estructura
   `f:[...]`, la misma fase se copia en R, S y T, produciendo un trifásico perfectamente
   balanceado ficticio: VUR 0, IUR 0, neutro 0. Falso negativo sistemático de las alertas de
   desbalance. *(Resuelto por el backend: soporte monofásico 1P2W — ver
   `specs/metrologia-monofasica.md` y migración `1f2e3d4c5b6a`.)*

---

## 9. Qué hay que hacer, en orden

**Frontend (bloqueante para que el dashboard funcione):**

1. Ampliar `EstadoFactorPotenciaSchema` y `EstadoTensionSchema` con `SIN_DATOS`
   (`src/core/schemas/telemetria.ts:5-6`).
2. Manejar `SIN_DATOS` en `LatestReadingCard.vue:34-40`.
3. Quitar cualquier compensación horaria propia sobre `registrado_en`.
4. Revisar formateos que asuman número en `desbalance_corriente_porcentaje`.

**Recomendado:**

5. `telemetry.ts:55` de `.parse()` a `.safeParse()`.

**A decidir en conjunto:** los cinco puntos de la sección 8.
