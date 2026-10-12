# Descartes de THD observables en el journal

> **Issue:** datamaq-automation/datamaq#5 · **Rama:** `feat/issue-5-validar-thd-ingesta`
> **Spec del padre:** `specs/thd-descartes-observables-y-renovacion-tiempo-real.md` (bloque A)

## 1. Objetivo y Contexto

Todo `harmonics` descartado tiene que dejar una línea en el journal con el motivo. Así, la próxima prueba de campo
de Hogar (`D48C49F03564`, fw V1.3.0) muestra por sí sola si falló el parser o la ventana.

El 2026-10-09 el único `harmonics` de Hogar llegó 369 s después de la última fila persistida de `inst`. Quedó fuera de
la ventana de 360 s (`granularidad + 60 s`) y no se guardó. Los dos descartes posibles (`harmonics_sin_thd_valido` y
`harmonics_sin_fila_en_ventana`) se logueaban en DEBUG, que no llega al journal, así que no queda rastro de cuál de los
dos ocurrió.

**Fuera de alcance:** cambiar la ventana de 360 s y persistir `harmonics` sin una fila de `inst`.

## 2. Dominio & Puertos

Sin cambios. `parsear_thd_harmonics` (dominio) y `RepositorioTelemetriaPort.actualizar_thd_instantanea` quedan igual.

## 3. Caso de uso & DTOs

`IngestarHarmonicsThdUseCase.ejecutar` (`src/application/use_cases/ingestar_harmonics_thd.py`):

| Descarte | Evento (nivel INFO) | Campos |
|---|---|---|
| El parser no extrae THD válido | `harmonics_sin_thd_valido` | `dispositivo_id`, `motivo="payload_sin_thd_parseable"`, `claves_payload` |
| No hay fila persistida en la ventana | `harmonics_sin_fila_en_ventana` | `dispositivo_id`, `motivo="sin_fila_persistida_en_ventana"`, `ventana_s` |

- Se conservan los dos nombres de evento, que ya se buscaban en los logs, y se agrega `motivo` a cada uno.
- `claves_payload` lleva las claves de primer nivel ordenadas, **nunca los valores**. Si el payload no es un objeto,
  lleva `["<tipo>"]`. Esto alcanza para contrastar el formato de V1.3.0 contra `parsear_thd_harmonics` sin volcar
  ~2 KB por mensaje al journal. Función: `claves_primer_nivel(payload)`.
- Un THD guardado no loguea nada nuevo.

## 4. Matriz de Pruebas (RED Suite)

`tests/unit/test_ingesta_harmonics.py`, con un logger falso que registra nivel, evento y campos:

| Test | Verifica |
|---|---|
| `test_descarte_por_parser_loguea_en_info_con_motivo_y_solo_las_claves` | INFO, `motivo`, claves ordenadas; ningún valor del payload en el log |
| `test_descarte_por_ventana_loguea_en_info_con_motivo_y_ventana` | INFO, `motivo`, `ventana_s=360` con granularidad 300 |
| `test_thd_guardado_no_loguea_descarte` | Sin registros cuando el repositorio guarda |
| `test_claves_primer_nivel_de_un_payload_que_no_es_dict_informa_el_tipo` | Payload que no es dict → `["<list>"]` |

## 5. Criterios del Gauntlet

`./scripts/pre-push.sh` en verde: arquitectura, tamaño, ruff, pyright y tests unitarios con cobertura ≥ 85 %.

## 6. Notas de implementación

- `907b7d3` (`test(unifilar)`, Durax 848,4 kW) tenía el mismo diff (blob `6ebe3d3→a744567`) que `a25a90f`, que ya
  está en `origin/main` (PR #4). Al rebasear la rama sobre `origin/main` git lo descartó como ya aplicado. La rama
  ya no lo lleva.
- Verificación en producción (la hace el padre): con Hogar reconfigurado, el journal muestra filas con THD
  (`thd_*_no_nulos > 0`) o una línea INFO de descarte con su motivo.
