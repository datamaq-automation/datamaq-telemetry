# Spec: Ingesta del THD por fase desde el topic `/harmonics` (repo `datamaq-telemetry`)

> **Estado:** implementado en local (commits `41f5c79`, `7008199`, `bd3d521`, `b142ae6`), sin push. Validación con datos reales **bloqueada** por una acción de hardware del dueño (habilitar `/harmonics` en un equipo).
> **Origen:** `specs/ingesta-harmonics-thd.md` del repo padre (`datamaq-2c`, commiteada en el padre).
> **Decisiones aplicables:** `decisions/2026-10-09_alcance-thd-y-umbral-fiabilidad.md`.
> **Traspasada a hija:** sí · **Bloque cerrado:** no (falta validación con datos reales).

## 1. Objetivo y Contexto

**Objetivo:** que el THD_V y el THD_I por fase publicados por el SmartPlus en `/harmonics` se persistan en `thd_v_r/s/t` y `thd_i_r/s/t`, para que la UI y `thd_i_fiable` tengan dato real.

**Alcance:**
- Despachar el subtópico `harmonics` en `ingestar_telemetria.py` hacia un caso de uso que lea THDv y THDi por fase y los una a la lectura instantánea del mismo dispositivo.
- Validar el payload (tipos, valores finitos y no negativos, fase 0/1/2 → R/S/T por número y no por posición).
- Tests con `harmonics.json` del backup como fixture literal (copia byte a byte en `tests/fixtures/`).

**Fuera de alcance:** los 25 armónicos individuales, tabla o endpoint de armónicos, cambiar firmware o configuración de equipos, UI, consultas a producción, push, `datamaq-data`.

## 2. Dominio & Puertos

- **Parser puro** `src/domain/telemetria/servicios/harmonics_thd.py`: `parsear_thd_harmonics(payload) -> dict[str, ThdFase]`. Stdlib. Mapea por el número de fase (0→R, 1→S, 2→T). Descarta por fase valores no numéricos, booleanos (`True` no es un número), no finitos o negativos. **No descarta por magnitud**: un THDi de 992,5 % se conserva. Su fiabilidad la decide `calidad_thd_i` (`thd_i_fiable`). Nunca lanza ante payload malformado.
- **Puerto** `RepositorioTelemetriaPort.actualizar_thd_instantanea(dispositivo_id, momento, ventana_s, thd) -> bool` en `src/domain/telemetria/ports.py`. Tiene implementación por defecto no-op: así los fakes de test que implementan el puerto no tienen que cambiar.

## 3. Casos de Uso & DTOs

**Estrategia de unión (aprobada por el padre):** actualizar la **última fila persistida** de `telemetry_instantaneous` del mismo `device_id` dentro de la ventana `(momento − ventana, momento]`, con `ventana = granularidad_segundos + 60 s` (`ventana_thd_s()` en `src/application/use_cases/ingestar_harmonics_thd.py`).

**Por qué esta estrategia y no una tabla aparte:**
- `/inst` solo persiste una fila cada `granularidad_segundos` (300 s, `ingestar_telemetria.py`, bloque de `debe_persistir`). Una ventana de pocos segundos dejaría casi todo `/harmonics` sin fila.
- Una tabla aparte exige migración Alembic (cabeza fijada en `tests/unit/test_migraciones.py::REVISION_HEAD`). No se creó migración porque el esquema actual ya tiene las columnas.

**Trade-offs:**
- Ventaja: sin migración. Cada fila sigue siendo una foto de un instante para la UI y el auditor.
- Desventaja 1: el THD queda asociado a la fila persistida más reciente, que puede tener hasta `granularidad + 60 s` de antigüedad. No es el mismo instante exacto.
- Desventaja 2: si llegan varios `/harmonics` en la misma ventana, gana el último.
- Desventaja 3: si `/harmonics` llega sin fila persistida en la ventana, se descarta con log. No hay reintento.

**Riesgo conocido (salvedad aprobada por el padre, no es un bug):** `thd_i_fiable` se calcula con la corriente de la fila persistida, que puede diferir hasta ~5 min del instante en que se midió el THD. Si la carga cambió en ese lapso, la fiabilidad puede quedar mal clasificada. Esto está fijado en `tests/unit/test_ingesta_harmonics.py` (test de ventana) y en el docstring de `ventana_thd_s`.

**Despacho:** `IngestarTelemetriaUseCase.ejecutar` llama a `IngestarHarmonicsThdUseCase` cuando el subtópico es `harmonics`. No se retransmite en vivo (no es una instantánea). El despacho queda fácil de extender para otros subtópicos de THD. **No** se implementa el topic `home/{id}/thd/v1` del firmware HOME V2.5.3 del catálogo: solo se deja el despacho sin estorbarlo.

## 4. Matriz de Pruebas

| Caso | Dónde | Estado |
|---|---|---|
| Fixture literal: R=(2,56; 992,52), S=(2,59; 530,99), T=(2,56; 300,0) | `test_harmonics_thd_parser.py` | ✅ |
| THDi absurdo (992,5 %) se conserva tal cual | `test_harmonics_thd_parser.py`, `test_ingesta_harmonics.py` | ✅ |
| No depende del orden de la lista | `test_harmonics_thd_parser.py` | ✅ |
| Fase faltante no aparece / solo se guarda la presente | parser + `test_ingesta_harmonics.py` | ✅ |
| Número de fase fuera de rango se ignora | parser | ✅ |
| Valor no numérico, `NaN`, `bool` o negativo se descarta sin tumbar las demás fases | parser | ✅ |
| Payload malformado devuelve vacío y no lanza | parser, dispatch | ✅ |
| Actualiza la fila más reciente dentro de la ventana | `test_actualizar_thd_instantanea.py` (SQLite) | ✅ |
| Sin fila en la ventana devuelve `False` y no crea nada | `test_actualizar_thd_instantanea.py` | ✅ |
| Fila posterior al momento no se toca | `test_actualizar_thd_instantanea.py` | ✅ |
| Fase faltante no pisa las otras fases | `test_actualizar_thd_instantanea.py` | ✅ |
| Otro dispositivo no se actualiza | `test_actualizar_thd_instantanea.py` | ✅ |
| Ventana = granularidad + 60 s | `test_ingesta_harmonics.py` | ✅ |
| `harmonics` no crea instantánea ni se publica en vivo | `test_ingesta_harmonics.py` | ✅ |
| Payload malformado por el listener no tumba el despacho | `test_ingesta_harmonics.py` | ✅ |
| Regresión de ingesta existente | `test_mqtt_eco_comando_propio.py`, `test_use_cases.py`, etc. | ✅ |

**Pendiente (no es de este repo):** validación con datos reales. Requiere que un equipo publique `/harmonics`. Hoy no hay ningún equipo con evidencia de hacerlo (ver Prerrequisito).

## 5. Criterios del Gauntlet

- `./scripts/pre-push.sh` completo en verde, corrido **aislado** (sin otro proceso usando `.coverage`).
- `verify_architecture.py`: `domain/` solo stdlib. El módulo `telemetria_thd_actualizador.py` vive en `infrastructure/`.
- `verify_code_size.py`: el repositorio se partió en `telemetria_thd_actualizador.py` para no superar el límite de 550 líneas de archivo y el techo de 510 de la clase (ver commit `bd3d521`).
- Commits atómicos por capa (dominio, infraestructura, aplicación), en español, con el porqué en el cuerpo.

## Prerrequisito de hardware (acción del dueño)

Para validar con datos reales hace falta que el equipo de Hogar (`2812d2af`, fw V1.3.0) publique `/harmonics`. Hoy `enable: false` en el backup de configuración. Habilitarlo es acción del dueño en el equipo. No es delegable a esta sesión.

## Verificación cruzada (al cerrar)

- [x] Existe un camino de código que procesa `harmonics` (`ingestar_telemetria.py`, `elif subtopico == "harmonics"`).
- [ ] `scripts/auditar_produccion.py` (check `cobertura_telemetria`) muestra `thd_*_no_nulos > 0` en el equipo piloto. **Bloqueado** por el prerrequisito de hardware.
- [ ] La tarjeta `DistorsionArmonicaCard` muestra THD_V real en el equipo piloto. **Bloqueado** por lo mismo.
- [ ] `TODO.md` "Ingesta" y "Visualización" de THD se marcan recién con datos reales a la vista.
