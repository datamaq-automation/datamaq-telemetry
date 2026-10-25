# Spec — Glosario TI, paso 1 (renombrado sin cambio de comportamiento)

> Borrador para aprobación. Sin commit. Rama `refactor/ti-glosario-paso1` desde `origin/main` (462cf34).
> Decisión: `/home/agustin/proyectos_software/datamaq/decisions/2026-10-13_glosario-ti-polaridad-secuencia-asociacion.md`.
> `spec-issue-18.md` (untracked, de la tarea anterior) queda fuera de este commit.

## 1. Objetivo y alcance

Paso 1 de tres: renombrar en **dominio y DTOs**, empezando por `RotacionFasorial` (`4bf4682`, en `origin/main`).
El mapper del YAML lee nombres viejos y nuevos. Sin cambio de valores, sin migración de datos, sin tocar
`payload_telemetria_parser.py:291-300`.

## 2. Mapa de renombrado: dónde aparece hoy

### 2.1 `RotacionFasorial` (`src/domain/telemetria/value_objects.py:282-300`)
- Campo `orden_fases: tuple[str, ...]` (l. 288) y `invertida: bool` (l. 289).
- Usado por `src/domain/telemetria/servicios/diagnostico_ti.py:63`.
- Tests: `tests/domain/telemetria/test_value_objects_ti.py` (usa `CandidatoTI`, no `RotacionFasorial` directo).

### 2.2 `CandidatoTI` (`value_objects.py:333-350`)
- `orden_fases` (l. 335) e `invertido` (l. 336). Usado por `diagnostico_ti.py:115-130`.
- Salida de la API: `src/application/services/diagnostico_ti_app_service.py:123-124` (claves `"orden_fases"`, `"invertido"`).

### 2.3 Dispositivo (`src/domain/telemetria/entities.py`)
- `invertido: bool | None` (l. 165), `correccion_angular_fases: str | None` (l. 164), `orden_fases: list[str] | None` (l. 166).
- Auditoría por nombre de campo: `entities.py:178-180` (`"correccion_angular_fases"`, `"invertido"`, `"orden_fases"`).
- Entidad de instalación: `entities.py:241-243`.

### 2.4 DTOs
- `src/application/dtos/dispositivo_dto.py`: lectura `invertido` (l. 26), `orden_fases` (l. 27), `correccion_angular_fases` (l. 23); escritura/PATCH `correccion_angular_fases` (l. 41), `invertido` (l. 42), `orden_fases` (l. 43).
- `src/application/dtos/telemetria_dto.py:188`: `secuencia_fases: str = "DIRECTA"` (**ya existe**, ver 3.2).

### 2.5 Mappers y uso
- YAML: `src/infrastructure/yaml/repositories/organizaciones_repository.py:362-364` (`m.get("correccion_angular_fases")`, `m.get("invertido")`, `m.get("orden_fases")`).
- Entidad↔DTO: `src/application/mappers/dispositivo_mapper.py:40-42, 68-70`.
- Caso de uso PATCH: `src/application/use_cases/gestionar_dispositivos.py:152-157`.
- Resolución: `src/application/use_cases/ingesta/resolvedor_dispositivo.py:51-54`.
- Ingesta: `src/application/use_cases/ingestar_telemetria.py:222-223`.
- Parser (**no tocar**): `src/application/mappers/payload_telemetria_parser.py:102` (`correccion_angular_fases`), `:291-300` (exclusión silenciosa, paso 3), `:348-369` (`orden_fases`, `invertido` como kwargs).
- Aplicación de la configuración: `src/application/mappers/fase_parser.py:158-205` (`invertido`, `orden_fases`).
- Persistencia: `src/infrastructure/sqlalchemy/repositories/dispositivos_repository.py:36, 88, 107` (columna `ct_phase_angle_offsets`).
- Admin/auditoría: `src/infrastructure/fastapi/routes/admin_router.py:111-113`.
- Router: `src/infrastructure/fastapi/routes/dispositivos_router.py:98` (lista de campos `correccion_angular_fases`).

### 2.6 Tests que hoy usan los nombres
- `tests/unit/test_auditoria_cambios_ti.py` (claves `"invertido"`, `"correccion_angular_fases"`, asserts de `c["field"]`).
- `tests/unit/test_yaml_organizaciones_repository.py:274-297` (valores `"R:180,S:-120"` y `"R:-60,S:60"`).
- `tests/unit/test_fase_parser.py:18-49` (`invertido=`, `orden_fases=`).
- `tests/domain/telemetria/test_value_objects_ti.py` y `tests/application/services/test_diagnostico_ti_app_service.py` (`orden_fases=`, `invertido=`).
- `tests/unit/test_datos_maestros_medidor.py:59-66`.

### 2.7 Lo que ya existe con los nombres nuevos
- `secuencia_fases`: `telemetria_dto.py:188`, `analizador_fasorial.py:39,229`, `telemetria_mapper.py:292`, `evaluador_anomalias_fases.py:240-262`. Es un **string** `"DIRECTA"`/`"INVERSA"`.
- `polaridad_ti`, `asociacion_tension_corriente`: no existen en `src/` ni `tests/`.

## 3. Conflictos de nombre que requieren tu decisión (antes de codificar)

**3.1 `invertido` es un bool global por dispositivo, no por fase.** La decisión pide `polaridad_ti` **por fase**. Eso es un cambio de modelo, no de nombre. Propuesta para el paso 1:
- `RotacionFasorial.invertida` → `polaridad_ti: bool` (global, mismo significado).
- Dispositivo e YAML: el campo nuevo se llama `polaridad_ti` (bool global por ahora). El mapper acepta `invertido` y `polaridad_ti`; si vienen los dos, gana `polaridad_ti`.
- La versión por fase queda para el paso 2/3.

**3.2 `orden_fases` no es `secuencia_fases`.** `orden_fases` en `RotacionFasorial` es la **permutación de fases lógicas** que aplica `fase_parser.aplicar_configuracion_ti` (`fase_parser.py:170-205`), es decir, la asociación tensión-corriente, no la secuencia de red. Además `secuencia_fases` ya existe como `str` "DIRECTA"/"INVERSA" (2.7), así que renombrar `orden_fases` a `secuencia_fases` mezcla dos tipos y dos conceptos. Propuesta: `orden_fases` → `asociacion_tension_corriente` (por fase, `tuple`), y `secuencia_fases` queda como está. Confirmá si la decisión quiso eso.

**3.3 `correccion_angular_fases` no es un rename en el paso 1.** La decisión dice que pasa a derivada (paso 2/3). Renombrarla en el paso 1 sin cambiar su uso como dato de entrada (`payload_telemetria_parser.py:102`, columna `ct_phase_angle_offsets`) cambiaría el contrato del YAML y de la API. Propuesta: el paso 1 **no renombra** `correccion_angular_fases`. Solo se mantiene y se documenta como "no verificada en campo". Si querés el renombrado de todos modos, hay que decidir a qué nombre.

**3.4 Auditoría.** `test_auditoria_cambios_ti.py` compara claves por nombre (`c["field"] == "invertido"`). Si la clave de auditoría cambia, el historial previo deja de compararse. Propuesta: la auditoría sigue escribiendo el nombre viejo hasta el paso 2.

**3.5 Columnas y datos.** Los nombres de columna (`ct_phase_angle_offsets`, `ct_inverted_phases`) y el YAML `datamaq-data` no cambian en el paso 1.

## 4. Matriz de tests

| # | Tipo | Qué prueba | Estado |
|---|---|---|---|
| C1 | compat (nuevo) | YAML con `invertido`, `orden_fases`, `correccion_angular_fases` produce el mismo `Dispositivo` que hoy | RED: no existe el test |
| C2 | compat (nuevo) | YAML con `polaridad_ti` (nombre nuevo) produce el mismo `Dispositivo` que `invertido` | RED: depende de 3.1 |
| R1 | existentes | `test_auditoria_cambios_ti`, `test_yaml_organizaciones_repository`, `test_fase_parser`, `test_value_objects_ti`, `test_diagnostico_ti_app_service` siguen verdes sin cambiar expectativas | verdes hoy |

## 5. Commits planificados (Conventional, en español, uno por capa)

1. `refactor(dominio): renombrar invertida a polaridad_ti en RotacionFasorial` — solo `value_objects.py`, `diagnostico_ti.py`, y tests de dominio.
2. `refactor(aplicacion): renombrar en DTOs y mapper, con compatibilidad del YAML viejo` — DTOs, `dispositivo_mapper.py`, `organizaciones_repository.py`, `fase_parser.py`, tests de compat C1/C2.
3. Si hace falta: `chore(...)` para tooling, separado.

Cada commit debe dejar la suite verde.

## 6. Criterio de aceptación

- Gauntlet local en verde: `APP_ENV=test ./scripts/pre-push.sh`.
- Ningún valor cambia: `R:180,S:-120` queda igual; `978f357` y la auditoría no cambian.
- Ningún archivo de `datamaq-data` ni del VPS cambia.
- Ningún push, PR ni consulta a producción.

## 7. Pendiente de aprobación

Para empezar necesito tu respuesta a 3.1, 3.2 y 3.3. La propuesta por defecto es la que está escrita en cada punto.
