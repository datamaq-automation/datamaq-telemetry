# Spec: THD_I con indicador de fiabilidad (bloques B2–B3)

> **Estado:** B1 cerrado (`3a62583`, `091fd36`, local, sin push). **B2 implementado** (commits `829b997`, `eb4c0fa`, `9dfbe29`, local): umbral 10 % de la corriente nominal del TI declarada en YAML, `None` sin TI declarado. **B3 bloqueado:** falta definir "período" (`desde`/`hasta` o ventana fija) y qué dispositivo mide el nodo de cabecera. Ver decisión `decisions/2026-10-09_alcance-thd-y-umbral-fiabilidad.md`.
>
> **Corrección vs. el texto de abajo:** la decisión del dueño fija el umbral en 10 % de la corriente nominal del TI (opción b), no un mínimo absoluto en amperios. El campo YAML es `corriente_nominal_ti_a` por medidor, con clave por fase (`{R: 100, S: 100, T: 150}`), bajo `medidores[]` de `organizaciones.yml`. Lo carga `datamaq-data`; el valor lo aporta el dueño.
> **Origen:** bloque `datamaq-telemetry` de `/datamaq/specs/thd-visualizacion-calidad-energia.md` (padre `datamaq-2c`).
> **Repo:** `datamaq-telemetry` · **Traspasada a hija:** parcial (B1 y diseño de B2) · **Bloque cerrado:** no

## 1. Objetivo y Contexto

**Objetivo:** que el backend deje de citar una norma no verificada y entregue a la app un
indicador de fiabilidad del THD_I.

**Alcance:**
- **B1 — Rotulado honesto:** reemplazar "IEEE 519" por "umbral interno" donde se atribuya el
  15 % de THD_I (`balance_energia.py:32,62`, tests de `test_balance_energia_sge.py`, mensajes de
  diagnóstico y docstrings). No cambia el valor ni la lógica. Si algún texto llega a la UI, avisar
  al padre.
- **B2 — `thd_i_fiable`:** agregar `thd_i_fiable: bool | None` a `MedicionFaseDTO` por fase,
  calculado a partir de `current_*` contra un mínimo configurable. **El valor por defecto y su
  origen esperan la decisión 1 del dueño.** La hija escribe ahora las secciones 2–5 de su spec
  y **no implementa B2** hasta que el padre le confirme el valor y el origen.
- **B3 — Balance SGE:** `thd_i_promedio_pct` se obtiene de las lecturas del período con el mismo
  criterio de fiabilidad, en vez del Query param. Cambiar el contrato del Query requiere aviso
  previo al padre. Depende de B2.

**Fuera de alcance:** topic `/harmonics`, tabla de armónicos individuales (Bloque C); calcular TDD
(faltan IL e Isc); consultar la DB de producción sin autorización del dueño.

**Certezas verificadas en este repo:** `balance_energia.py:32` (15.0) y `:56`;
`consultar_balance_energia.py:22,58,72` propaga el valor sin leerlo de ningún repositorio;
`models.py:168-172` guarda `thd_i_r/s/t`; no hay relación de TI por fase en `organizaciones.yml`.

## 2. Dominio & Puertos

**Estado actual verificado:**
- `MedicionFaseDTO` (`src/application/dtos/telemetria_dto.py:18-28`) tiene `current_A` y `thd_i_pct`, sin `thd_i_fiable`.
- El único constructor es `TelemetriaMapper.fase_to_dto` (`src/application/mappers/telemetria_mapper.py:90`). Toma `fase.corriente.amperios` y `fase.thd_i_porcentaje`.
- `ResultadoBalanceEnergia.thd_i_promedio_pct` existe (`balance_energia.py:24`); `evaluar_balance` solo compara.

**Regla de dominio propuesta (B2):**
- Nueva función pura en `src/domain/telemetria/` (stdlib, sin dependencias externas), por ejemplo `es_thd_i_fiable(corriente_a: float | None, minimo_a: float | None) -> bool | None`.
  - `corriente_a is None` → `None`.
  - `minimo_a is None` (mínimo sin configurar) → `None`. **No se elige un default silencioso.**
  - `corriente_a >= minimo_a` → `True`; si no → `False`.
- La función no conoce el origen del mínimo. Recibe un valor ya resuelto en amperios.

**Configuración del mínimo (diseñada para encajar en ambas opciones sin rediseño):**
- Un único punto de resolución, puerto `ProveedorMinimoCorrienteTI` (en `domain/…/ports.py`) con un método `minimo_corriente_a(dispositivo_id: str) -> float | None`.
- Dos adaptadores posibles, elegidos por configuración, no por código:
  - **Opción (a) — absoluto:** `minimo_corriente_a` devuelve un valor fijo en amperios, leído de settings (`THD_I_CORRIENTE_MINIMA_A`, sin default).
  - **Opción (b) — porcentaje de la nominal del TI:** devuelve `porcentaje * corriente_nominal_ti_a`, con `corriente_nominal_ti_a` leída de `organizaciones.yml` por fase (campo aún no existe; lo carga `datamaq-data` si el dueño elige (b)).
- Mientras no haya decisión, el adaptador por defecto devuelve `None` → `thd_i_fiable = None` en todas las fases. La app lo trata como `false`. Así B2 puede mergearse sin fijar el valor.

**Trasfondo de lectura de `current_*`:** se usa la corriente de la misma lectura de la fase; no se promedia en esta capa.

## 3. Casos de Uso & DTOs

**Cambio de contrato (aditivo, sin romper clientes):**
- `MedicionFaseDTO` suma `thd_i_fiable: bool | None = None` (default `None` = "no determinado", coherente con la regla del contrato).
- `MedicionFaseSchema` en la app: `thd_i_fiable?: boolean | null` (fuera de este repo; avisar al padre cuando se mergee).

**Mapeo (B2):**
- `TelemetriaMapper.fase_to_dto` recibe el mínimo resuelto (o el proveedor inyectado) y calcula `thd_i_fiable` con la función de dominio. No se cambia la firma pública de `fase_to_dto` sin revisar sus llamadores (`grep -rn fase_to_dto src`).

**B3 — balance SGE:**
- `ConsultarBalanceEnergiaUseCase.ejecutar` (`consultar_balance_energia.py:22`) hoy recibe `thd_i_promedio_pct` como parámetro desde el Query (`sge_router.py:279`).
- Propuesta: el caso de uso calcula el promedio de `thd_i_pct` **solo sobre fases con `thd_i_fiable is True`** de las lecturas del período. Si ninguna fase es fiable → `None` (el diagnóstico por THD no se dispara).
- **Compatibilidad:** el Query param se mantiene un ciclo como override explícito (deprecado). Quitarlo requiere aviso previo al padre (ver bloque B3).
- B3 **depende de B2** y no puede implementarse antes.

## 4. Matriz de Pruebas

Todas las pruebas son unitarias, sin DB ni MQTT, con DTOs y valores en memoria.

| # | Caso | Esperado | Bloque |
|---|---|---|---|
| T1 | `es_thd_i_fiable(None, 1.0)` | `None` | B2 |
| T2 | `es_thd_i_fiable(5.0, None)` (mínimo sin configurar) | `None` | B2 |
| T3 | `es_thd_i_fiable(0.022, 1.0)` | `False` | B2 |
| T4 | `es_thd_i_fiable(1.0, 1.0)` (límite inclusivo) | `True` | B2 |
| T5 | Adaptador (a): mínimo 1.0 A leído de settings | `minimo_corriente_a` devuelve 1.0 | B2 |
| T6 | Adaptador (a) sin setting | devuelve `None` | B2 |
| T7 | Adaptador (b): 0,1 × 5 A nominal | devuelve 0.5 | B2 (solo si el dueño elige (b)) |
| T8 | `fase_to_dto` con corriente bajo mínimo | `thd_i_fiable=False`, `thd_i_pct` intacto | B2 |
| T9 | `fase_to_dto` sin corriente | `thd_i_fiable=None` | B2 |
| T10 | Schema JSON: DTO sin campo nuevo (cliente viejo) | serializa con `thd_i_fiable: null` | B2 |
| T11 | B3: fases [fiable 22 %, no fiable 992 %] | promedio = 22 % (la no fiable excluida) | B3 |
| T12 | B3: ninguna fase fiable | `thd_i_promedio_pct = None`, sin diagnóstico THD | B3 |
| T13 | B3: Query param presente y deprecado | se usa el override y se loguea advertencia | B3 |
| T14 | Regresión `evaluar_balance` (`test_balance_energia_sge.py`) | sin cambios de valor ni de estado | B1–B3 |

Fixtures: el caso real del backup `harmonics.json` (fase 0: fundamental 0,022 A, THDi 992,5 %) se usa como dato de referencia en T3, extraído de `backups/powermeter_20260814_155719/harmonics.json`, no de la DB.

## 5. Criterios del Gauntlet

**Gauntlet local (`./scripts/pre-push.sh`) verde antes de cualquier commit de B2/B3:**
- Stage 1: `__init__.py` de 0 bytes (no se crean módulos con contenido).
- Stage 2: `ruff check` + `ruff format --check`.
- Stage 3: `pyright` 0 errores (la función de dominio debe tipar `float | None`).
- Stage 4: unitarias con cobertura ≥ 85 %, incluyendo T1–T14 según bloque.
- Stage 5: integración (`tests/integration/`).
- Stage 6: `verify_architecture.py` (`domain/` solo stdlib) y `verify_code_size.py` (ningún archivo > 500 líneas).

**Entorno de tests:** `DB_HOST=127.0.0.2 DB_PORT=1` para no tocar la DB real (memoria del proyecto: tests locales). Salida del gauntlet a archivo, no con `| tail`.

**Commits atómicos (AGENTS.md del padre §4):** dominio (función + tests) → aplicación (DTO + mapper + caso de uso) → router si cambia el Query. Tooling separado en `chore(...)`. Staging explícito por archivo.

**Push:** no autorizado. CI/CD no aplica hasta que haya push.
