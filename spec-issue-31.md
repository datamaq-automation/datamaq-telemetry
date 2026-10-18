# Spec — Issue datamaq-automation/datamaq#31: compuerta de calidad de datos y cobertura por fase en el MCP

> Borrador para revisión. Sin commit, sin código. Rama de referencia: `ops/issue-23-chequeo-permisos-src` (no se toca).
> Archivos de referencia: `tools/mcp/server.py` (420 líneas), con numeración de la lectura actual.

## 1. Estado verificado

- **Las cinco tools no calculan igual.**
  - `datamaq_consultar_potencia_reciente` (`server.py:340-410`) es la única que agrega por dispositivo en el MCP: lee `/api/v1/telemetria/instantaneous/{id}` por medidor (`:367-379`), agrega en `_agregar_serie_planta` (`:293-332`) y calcula el FP global (`:388`).
  - `datamaq_analizar_capacitores` (`:208-235`) y `datamaq_consultar_penalizaciones` (`:239-266`) **no calculan**: pasan la respuesta del backend (`/api/v1/analitica/...`). La compuerta en el MCP solo puede mirar lo que devuelve el backend, o consultar datos por medidor aparte.
  - `datamaq_consultar_alertas` (`:157-204`) es la fuente de alertas abiertas, con `dispositivo_tag` por medidor.
  - `datamaq_listar_plantas` (`:142-153`) solo lista.
- **Hay un defecto que oculta el signo.** `_agregar_serie_planta` calcula `fp_bucket = abs(p_val) / s_val` (`server.py:323`), y el FP global usa `abs(p_acum)` (`:388`). Un medidor con P negativa sigue dando FP positivo. Por eso el FP no sirve como señal de la inversión de signo: la compuerta tiene que leer el signo de P **antes** del `abs`.
- **Alertas que ya existen en el backend y sirven de señal:**
  - `POLARIDAD_TI` (`src/domain/telemetria/servicios/evaluador_potencia_negativa.py:59`), con umbral `umbral_p_minima_w = -100.0` (`:22`).
  - `TI_INVERTIDO` (`src/domain/telemetria/servicios/evaluador_alertas_calidad.py:227-239`).
  - `FALTA_FASE` (`evaluador_alertas_calidad.py:112`, categoría `SUMINISTRO`).
  - `CRUCE_TI_FASE` (`src/domain/telemetria/servicios/evaluador_anomalias_fases.py:129`).
- **Fases por medidor:** `fases_con_ti` viene del YAML (`payload_telemetria_parser.py:281-283`). Un medidor con `fases_con_ti = "R,S"` mide solo R y S. El parser ya marca `R/S/T` ausentes (`:303-307`), pero la respuesta del MCP no lo expone.
- **Umbral de cobertura existente:** `server.py:408-409` agrega `advertencia_datos` si la cobertura de **puntos** es < 80%. No mira fases ni signo.

## 2. Decisión 1 — qué es "dato sospechoso" para la compuerta

Un medidor de la planta está **sospechoso** en la ventana si cumple **al menos una** de estas condiciones:

| Código | Condición | Umbral propuesto | Justificación |
|---|---|---|---|
| S1 | Alerta abierta `POLARIDAD_TI` o `TI_INVERTIDO` del medidor | cualquier alerta abierta | Es la señal que ya calcula el backend; el MCP la reutiliza en vez de recalcularla. |
| S2 | P negativa sostenida en un medidor de **consumo** | buckets de 5 min con `P < -100 W` ≥ 50% de los buckets con dato en la ventana | Mismo umbral que `evaluador_potencia_negativa.py:22`. El 50% evita que una inversión puntual dispare la compuerta. |
| S3 | Medidor sin datos suficientes | cobertura de buckets < 80% (mismo umbral que `server.py:408`) | Reusa el criterio ya existente, aplicado por medidor y no solo a la planta. |
| S4 | Cobertura de fases incompleta | `fases_con_ti` no es `R,S,T` | No es un dato erróneo, pero el total del medidor no es trifásico. Se marca para que no se lo tome como total. |

**Caso del 369:** S2 y S1 se disparan a la vez. El dato del 2026-10-06 al 2026-10-13 tiene P negativa en R y S (ver `scratchpad/horaria_369.txt`). S4 también se dispara, porque `fases_con_ti = "R,S"`.

**Pregunta abierta:** la compuerta S2 supone que el medidor es de **consumo**. El MCP no tiene el tipo de medidor en la respuesta. Propongo leer `tipo_instalacion` si el backend lo expone, y si no, aplicar S2 a todos y marcarlo en la respuesta. Hay que confirmar con el backend (`/api/v1/dispositivos`).

## 3. Decisión 2 — qué responde la tool cuando la compuerta se activa

**Recomendación: bloquear el número de recomendación y devolver el diagnóstico con advertencia explícita.**

- **Si S1 o S2 están activas** (sospecha de signo): `datamaq_analizar_capacitores` y `datamaq_consultar_penalizaciones` **no devuelven** kVAr recomendados ni importes. Devuelven `estado: "bloqueado_por_calidad_de_datos"`, la lista de medidores sospechosos con sus códigos, y el motivo. Razón: con P invertida, el FP y la potencia reactiva que se usan para dimensionar capacitores son incorrectos, y un número plausible es más peligroso que ninguno. Es exactamente el riesgo de `analizar_capacitores` del caso del 369.
- **Si solo S3 o S4 están activas** (datos incompletos o fase faltante): la tool **devuelve el cálculo** con `advertencia_datos` y el detalle por medidor, porque el número sigue siendo informativo y el usuario puede decidir.
- **`datamaq_consultar_potencia_reciente`:** nunca bloquea. Devuelve siempre los agregados, con los medidores sospechosos listados en `medidores_sospechosos`.

Razón de la diferencia: el signo invierte el resultado (no solo lo degrada), mientras que la falta de cobertura solo le quita precisión.

## 4. Decisión 3 — cobertura por fase sin tratar la falta como cero

- Por medidor, la respuesta incluye `fases_medidas` (por ejemplo `["R","S"]`) y `fases_faltantes` (por ejemplo `["T"]`), tomados de `fases_con_ti` del YAML.
- Cada fase tiene un valor **explícito**: `null` si no se mide, nunca `0`.
- En los totales de planta, si algún medidor no es trifásico, se devuelve `total_trifasico_completo: false` y el total se marca como "parcial". No se rellena la fase faltante con cero.
- `_agregar_serie_planta` (`server.py:293-332`) no suma `None` como cero: en `:306-308` ya hay un `if p_w is not None`, pero el total de un medidor de dos fases hoy es la suma R+S sin marca. El cambio es marcar, no cambiar el cálculo de R+S.

## 5. Decisión 4 — qué tools se afectan

| Tool | Línea | ¿Afectada? | Cambio |
|---|---|---|---|
| `datamaq_consultar_potencia_reciente` | `:340-410` | **Sí** | Compuerta con `medidores_sospechosos`, cobertura por fase, lectura del signo antes de `abs` (`:323`). No bloquea. |
| `datamaq_analizar_capacitores` | `:208-235` | **Sí** | Bloquea el kVAr si hay S1 o S2. Advertencia si S3 o S4. Requiere datos por medidor (ver pregunta abierta). |
| `datamaq_consultar_penalizaciones` | `:239-266` | **Sí** | Mismo criterio que capacitores: bloquea importes si hay S1 o S2. |
| `datamaq_consultar_alertas` | `:157-204` | **No** (es la fuente) | Sin cambio. Se usa como entrada para S1. |
| `datamaq_listar_plantas` | `:142-153` | **No** | Sin cambio. |

**Pregunta abierta:** `analizar_capacitores` y `penalizaciones` calculan en el backend. Para evaluar S2 y S4 por medidor, el MCP necesita datos por medidor, o el backend tiene que incluirlos en la respuesta. Propongo pedir el cambio al backend (agregar `medidores` a la respuesta) y, mientras tanto, que el MCP use S1 (de `/api/v1/alertas`) como única compuerta en estas dos tools. Si el backend no lo incluye, S2 y S4 no se aplican en estas dos tools, y hay que decirlo en la respuesta.

## 6. Matriz de tests RED (sin base real, fixtures en memoria)

| # | Fixture | Tool | Esperado | Por qué RED hoy |
|---|---|---|---|---|
| T1 | Medidor `P < -100 W` en 60% de los buckets, tipo consumo | `consultar_potencia_reciente` | `medidores_sospechosos` contiene el medidor con S2; `fp_bucket` no se calcula con signo positivo oculto | Hoy no hay `medidores_sospechosos` (`:394-407`) |
| T2 | Igual a T1 | `analizar_capacitores` | `estado == "bloqueado_por_calidad_de_datos"`, sin `kvar_recomendados` | Hoy devuelve el resultado del backend sin revisar |
| T3 | Igual a T1 | `consultar_penalizaciones` | Importes bloqueados | Hoy no revisa signo |
| T4 | Medidor con `fases_con_ti = "R,S"`, P válida | `consultar_potencia_reciente` | `fases_faltantes == ["T"]`, `total_trifasico_completo == false`, la fase T es `null` y no `0` | Hoy no hay cobertura por fase |
| T5 | Medidor con `fases_con_ti = "R,S"` | `analizar_capacitores` (solo S4) | Devuelve el cálculo con `advertencia_datos`, no bloqueado | Hoy no hay advertencia por fase |
| T6 | Planta con alerta `POLARIDAD_TI` abierta en un medidor | `consultar_alertas` → compuerta | El medidor queda con S1 | Hoy la alerta no se cruza con el cálculo |
| T7 | Medidor con cobertura de buckets 50% | `consultar_potencia_reciente` | S3 activa; advertencia por medidor además de la de planta | Hoy solo hay advertencia a nivel planta (`:408`) |
| T8 | Planta sana (P positiva, 3 fases, cobertura 100%) | las tres tools | Sin bloqueos, sin advertencias, resultado idéntico al de hoy | Regresión: el caso sano no debe cambiar |
| T9 | Medidor con P negativa en un bucket aislado (5%) | `consultar_potencia_reciente` | S2 **no** se activa | Verifica el umbral del 50% |

Los T1 a T4 y T8 se pueden escribir en `tools/mcp/test_server.py` con el cliente HTTP mockeado (`set_client`, `server.py:31`). Ningún test usa base real ni `data/`.

## 7. Preguntas que necesito que decidas

1. **Bloqueo vs advertencia:** ¿aceptás la recomendación de bloquear el kVAr y los importes con sospecha de signo (S1, S2), y solo advertir con S3 y S4?
2. **Tipo de medidor:** ¿el backend expone si un medidor es de consumo o de generación? Si no, S2 se aplica a todos.
3. **Datos por medidor en las dos tools del backend:** ¿pedimos al backend que incluya `medidores` en `analizar_capacitores` y `penalizaciones`, o aceptamos que solo S1 aplique ahí?
4. **Orden respecto del #23:** el #31 no depende del #23 (no toca systemd). Pero el #31 cambia `server.py`, y #23 cambia la unidad. No hay conflicto de archivos.

## 8. Qué no se hace

- Sin código ni tests en esta fase.
- Sin push ni PR.
- Sin tocar el VPS, credenciales ni datos. No se marca nada en la base (el marcado del 369 queda como está).
