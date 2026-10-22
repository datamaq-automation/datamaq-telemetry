# Spec: Metrología Monofásica (1P2W) y saneamiento de fases sin TI

## 1. Objetivo y Contexto

Corregir la física incorrecta que el backend aplica a instalaciones **monofásicas (1P2W)** y, en general, a cualquier fase sin transformador de corriente (TI) instalado.

**Problema real (medidor SmartPlus, instalación 1P2W):**

- Los tres bornes de tensión están **cableados en paralelo sobre la misma fase**: no hay desfasaje de 120°. Las mediciones de tensión R/S/T son válidas (casi idénticas) porque los tres sensores miden la misma fase.
- Los TIs de las fases S y T **no están conectados**: el firmware reporta corrientes residuales de ruido (0.10–0.20 A) en S/T.
- El backend interpreta esto como un sistema trifásico balanceado y produce **cuatro métricas falsas**:

| Columna | Valor falso actual | Física correcta |
| :--- | :--- | :--- |
| `voltage_linea_V` | `227 · √3 ≈ 397 V` | Tensión entre bornes en paralelo = 0 V → no aplica (NULL) |
| `desbalance_tension_porcentaje` | 0.15–0.21 % (tolerancia entre sensores) | No hay tres fases → no aplica (NULL) |
| `tension_neutro_estimada` | 0.0 V (fasores a 120° con V iguales) | No aplica (NULL) |
| `current_n` | suma fasorial de corrientes de ruido | No hay neutro trifásico → no aplica (NULL) |

**Bug de réplica (informe §8.5, deuda #5):** el payload compacto de una sola fase con clave raíz `{"n":"R","v":..,"i":..,"p":..,"q":..}` se replica a S y T vía el fallback `or payload`, fabricando un "trifásico balanceado" ficticio.

**Decisiones (D1–D4, aprobadas):**

- **D1.** Anular en la ingesta las corrientes residuales de fases sin TI, config-driven vía `fases_con_ti`. Fase sin TI → `corriente/P/Q/S/FP/THD_I = None`; **se conserva la tensión** (y su THD_V, que es una medida de tensión real).
- **D2.** Backfill histórico a `NULL` de las 4 columnas derivadas trifásicas (`voltage_linea_V`, `desbalance_tension_porcentaje`, `current_n`, `tension_neutro_estimada`) para dispositivos monofásicos.
- **D3.** El backfill **solo** toca esas 4 columnas derivadas; las corrientes S/T ruidosas históricas (mediciones crudas) no se modifican.
- **D4.** Eliminar el recálculo on-read de `current_n`/`tension_neutro_estimada` en el repositorio (hoy re-fabrica valores falsos al leer).

**Alcance:** `src/domain/telemetria/services.py`, `src/application/use_cases/ingestar_telemetria.py`, `src/application/use_cases/consultar_telemetria.py`, `src/infrastructure/sqlalchemy/mysql_repositories.py`, una migración Alembic y sus tests. Fuera de alcance: `scripts/provision_device.py` y la API de dispositivos (la config `tipo_instalacion`/`fases_con_ti` ya se gestiona por PATCH).

## 2. Dominio & Puertos

Entidades existentes (sin cambios de estructura):

- `Dispositivo.tipo_instalacion: str` (mapea a `devices.installation_type`) — topología/uso: `"3P4W"`, `"3P3W"`, `"1P2W"`, `"CONSUMO"`, `"GENERACION"`.
- `Dispositivo.fases_con_ti: str` (mapea a `devices.phases_with_ct`) — CSV de fases con TI: `"R,S,T"`, `"R,T"`, `"S,T"`, `"R"`.

**Predicado de monofásico** (única fuente de verdad, compartida por runtime y migración):

> `TRIM(UPPER(tipo_instalacion)) = '1P2W'` **o** `fases_con_ti` es una única fase (sin coma y no vacía).

Nuevos helpers en `AnalizadorCalidadEnergiaService` (dominio puro, sin dependencias externas):

- `es_instalacion_monofasica(tipo_instalacion, fases_con_ti) -> bool`
- `fases_con_ti_como_lista(fases_con_ti) -> set[str]` (normaliza CSV/lista/set a mayúsculas; `None`/vacío → `{"R","S","T"}`)
- `sanear_fase_sin_ti(fase: MedicionFase) -> MedicionFase` (conserva `tension` y `thd_v_porcentaje`; anula `corriente`, `potencia_activa`, `potencia_reactiva`, `potencia_aparente`, `factor_potencia`, `thd_i_porcentaje`)

## 3. Casos de Uso & Flujo

### 3.1 Ingesta (`IngestarTelemetriaUseCase.ejecutar`, subtópico `inst`)

1. Determinar `es_monofasico = es_instalacion_monofasica(dispositivo.tipo_instalacion, dispositivo.fases_con_ti)` y `fases_con_ti = fases_con_ti_como_lista(dispositivo.fases_con_ti)`.
2. **Honrar la clave raíz `n`:** si `payload["n"]` es una cadena no vacía, es un payload compacto monofásico declarado; solo esa fase recibe datos y las demás quedan vacías (sin réplica).
3. Resolver `data_r/s/t` como hoy (arreglo `f`, `phase_*`, `fase_*`, claves `r/s/t`, o fallback `payload` para el formato legacy con sufijos).
4. **Saneamiento D1:** para cada fase no presente en `fases_con_ti`, aplicar `sanear_fase_sin_ti`.
5. Calcular totales y métricas como hoy, pero si `es_monofasico` → las 4 métricas trifásicas quedan `None` (sin calcular desbalance, neutro ni tensión línea-línea).
6. **Alertas:** si `es_monofasico`, omitir `evaluar_alerta_desbalance` y auto-resolver las alertas `DESBALANCE_TENSION` abiertas.

### 3.2 Consulta (`ConsultarTelemetriaUseCase.listar_instantaneas`)

- Pasar `es_monofasico` a `agregar_lecturas_en_intervalo` para que la agregación no re-fabrique las 4 métricas trifásicas en buckets monofásicos.

### 3.3 Agregación (`AnalizadorCalidadEnergiaService`)

- `_agregar_grupo_lecturas(..., es_monofasico: bool = False)`: si `es_monofasico`, las 4 métricas quedan `None`; en caso contrario se calculan como hoy.
- `agregar_lecturas_en_intervalo(..., es_monofasico: bool = False)`: propaga el flag.

### 3.4 Lectura (`MySQLTelemetriaRepository._instantanea_to_entity`)

- `current_n`/`tension_neutro_estimada` se leen tal cual de la BD; si son `None`, quedan `None` (sin recalcular on-read). `voltage_linea_V` y `desbalance_tension_porcentaje` ya se leían tal cual.

## 4. Matriz de Pruebas (RED Suite)

`tests/unit/test_metrologia_monofasica.py` (nuevo) y `tests/unit/test_migraciones.py` (extendido):

| Escenario BDD | Contrato |
| :--- | :--- |
| Dado `tipo_instalacion="1P2W"` → monofásico | `es_instalacion_monofasica(...)` es `True` |
| Dado `fases_con_ti="R"` → monofásico | `es_instalacion_monofasica(...)` es `True` |
| Dado `tipo_instalacion="CONSUMO"`, `fases_con_ti="R,S,T"` → trifásico | `es_instalacion_monofasica(...)` es `False` |
| Dado `fases_con_ti="R,T"` (Aron 2-TI) → trifásico | `es_instalacion_monofasica(...)` es `False` |
| Dado una fase sin TI | `sanear_fase_sin_ti` conserva tensión y THD_V; anula corriente/P/Q/S/FP/THD_I |
| Dado payload compacto raíz `{"n":"R",...}` | solo fase R con datos; S y T vacías (sin réplica) |
| Dado dispositivo monofásico en ingesta | lectura persistida con las 4 métricas trifásicas en `None` |
| Dado dispositivo monofásico en ingesta | no se evalúa alerta de desbalance |
| Dado agregación con `es_monofasico=True` | bucket agregado con las 4 métricas trifásicas en `None` |
| Dado backfill con dispositivo `1P2W` | 4 columnas derivadas en `NULL` tras `upgrade head` |
| Dado backfill con dispositivo `phases_with_ct='R'` | 4 columnas derivadas en `NULL` tras `upgrade head` |
| Dado backfill con dispositivo trifásico | 4 columnas derivadas intactas |

## 5. Criterios del Gauntlet

- `.venv/bin/pytest tests/unit/` → 100% aprobados, cobertura de `src/` ≥ 85 %.
- `bash scripts/pre-push.sh` → Exit Code 0 (etapas 1-4).
- `ruff check .` y `ruff format --check .` → 0 errores.
- `pyright` (modo strict) → 0 diagnósticos.
- `agy-opt audit-dip` → 0 violaciones (sin `import logging` en `adapters/`).
- Migración: `down_revision = "c9d0e1f2a3b4"`, head lineal único; `tests/unit/test_migraciones.py` actualiza `REVISION_HEAD`.
