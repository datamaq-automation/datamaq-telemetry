# Latencia del unifilar en resumen e histórico

> **Issue:** datamaq-automation/datamaq#14 · **Rama:** `fix/issue-14-latencia-unifilar`
> **Spec del padre:** `specs/unifilar-timeout-resumen-historico.md` (bloque `datamaq-telemetry`)

## 1. Objetivo y Contexto

`GET …/unifilar/nodos/{nodo}/resumen` y `…/resumen/historico` tienen que responder en menos de 3 s (p95) para una
acometida con 2 dispositivos frontera, y cada request tiene que dejar su duración en el journal.

Producción (2026-10-11), acometida de Durax: `resumen` p50 5,7 s y p95 10,0 s; `historico` p50 3,7 s y p95 8,0 s. El
navegador corta a los 10 s (499 en nginx). Ninguna consulta aparece en el slow log. Los endpoints son síncronos y el
pool tiene 12 conexiones, en 2 vCPU compartidas con el worker MQTT.

**Fuera de alcance:** endpoints asíncronos, tamaño del pool y nginx.

## 2. Dominio & Puertos

Sin cambios de dominio ni de puertos. Los cambios son de infraestructura y de un caso de uso de aplicación.

## 3. Caso de uso & DTOs

Sin DTOs nuevos. Causas encontradas y cambios:

| Causa (perfilada) | Cambio | Dónde |
|---|---|---|
| `YamlOrganizacionesRepository` releía y parseaba todo `data/` en **cada** llamada (~165 ms por parseo en un Ryzen, más en el VPS): 42 parseos por `resumen` | Caché a nivel de módulo, invalidada por una firma de `os.stat` (ruta, mtime y tamaño de cada YAML, más el mtime de cada directorio). Un `git pull` de `data/` se ve sin reiniciar. Lock para el threadpool | `src/infrastructure/yaml/loaders.py` |
| `ConsultarTelemetriaUseCase` resolvía dispositivo, suscripción y plan en cada llamada por medidor | Memo en la instancia, que vive un request (`dependencies.py`) | `src/application/use_cases/consultar_telemetria.py` |
| Sonda `CONVERT_TZ` en cada `listar_ultimos_acumulados_por_periodo` | Una por zona y por instancia del repositorio (un request) | `src/infrastructure/sqlalchemy/repositories/telemetria_repository.py` |
| Sin medición de punta a punta | `DuracionRequestMiddleware`: `http_request_completado` en INFO con `metodo`, `ruta` (plantilla), `estado_http`, `duracion_ms` y `request_id` | `src/infrastructure/fastapi/duracion_requests.py` (server.py solo lo registra) |

## 4. Matriz de Pruebas (RED Suite)

| Archivo | Tests |
|---|---|
| `tests/unit/test_cache_yaml.py` | un parseo para N lecturas; un archivo modificado se ve sin reiniciar; un archivo nuevo invalida; instancias distintas comparten la caché; 8 hilos con la caché fría hacen 1 parseo; facturas también; la lista devuelta no es la cacheada |
| `tests/unit/test_duracion_requests.py` | ruta como plantilla sin IDs, método, estado, duración y `request_id` igual al header; 503; excepción no manejada = 500; 404 = `sin_ruta`; en `create_app` va por dentro de `RequestIdMiddleware` |
| `tests/integration/test_consultas_por_request_unifilar.py` | con el cableado real de `dependencies.py` sobre SQLite y una acometida MT con 2 medidores: `resumen` = 12 consultas, `historico` + referencia = 6, 1 parseo con la caché fría y 0 con la caliente; `devices` 1 vez por medidor, `organizations` 1 vez |

## 5. Criterios del Gauntlet

- **Local (criterio de cierre):** consultas y parseos por request, antes y después, con el perfilador sobre SQLite
  (2 medidores × 35 días a 5 min, acometida de Durax con el YAML real). Los milisegundos locales son indicativos.
- `./scripts/pre-push.sh` en verde con `APP_ENV=test`.
- **Post-deploy (lo verifica el padre):** p95 de `duracion_ms` < 3 s en los dos endpoints para la acometida de Durax,
  medido con `http_request_completado`.

| Request | Consultas SQL | Parseos de data/ | Tiempo local |
|---|---|---|---|
| `resumen`, antes | 26 | 42 | 9,2 s |
| `resumen`, después | 12 | 1 en frío, 0 en caliente | 1,7–2,0 s |
| `historico` + `potencia_referencia`, antes | 17 | 36 | 3,1 s |
| `historico` + `potencia_referencia`, después | 6 | 0 | 0,16–0,2 s |

## 6. Notas de implementación

- **Lo que queda en `resumen` (no se tocó):** las 6 lecturas de `telemetry_instantaneous` (2 últimas lecturas, 2 para la
  compensación histórica de 30 días a 5 min y 2 para la demanda cuartohoraria del mes) y el mapeo a DTO con
  diagnóstico de cada punto agregado (~30 % del tiempo restante en el perfil). Si el p95 de producción no baja de 3 s,
  los siguientes pasos son, en orden: (1) leer una sola vez las filas crudas por medidor para la compensación y la
  demanda; (2) que `calcular_historico` pida solo `(momento, P, Q)` sin construir el DTO completo con diagnóstico.
- **Aislamiento de la caché (pedido del padre):** `_cargar_con_cache` devuelve `copy.deepcopy` del resultado (~0,5 ms con
  el `data/` real, contra ~165 ms de un parseo). Auditoría de los callers en `src/`:
  `YamlOrganizacionesRepository._cargar_organizaciones_raw` (9 métodos de lectura), `obtener_facturas_planta`
  (`cargar_facturas_distribuidora`) y `system_router._validar_datamaq_data`. Ninguno muta el resultado; el único
  `append` (`listar_plantas`) es sobre una lista local. Pero `obtener_instalacion_medidor` pasaba la lista
  `orden_fases` cacheada por referencia a la entidad. La copia profunda cierra esa clase de error para los
  consumidores actuales y los futuros. Tests: `test_mutar_el_resultado_no_corrompe_la_cache`,
  `test_una_lista_que_escapa_a_una_entidad_no_es_la_de_la_cache` y `test_facturas_mutadas_no_corrompen_la_cache`.
  Los tres fallan con la copia superficial anterior.
- `server.py` sube de 530 a 532 líneas en esta rama (límite 550). La rama de #15 lo baja a 526. Las dos ramas tocan
  líneas distintas.
- El middleware loguea todos los requests HTTP, incluido `/health`: una línea por request en el journal.
