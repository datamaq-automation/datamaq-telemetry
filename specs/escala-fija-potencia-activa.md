# Escala vertical fija en el gráfico de potencia activa: `X-Potencia-Referencia-W`

> **Origen:** bloque `## Repo: datamaq-telemetry` de `../specs/escala-fija-potencia-activa.md` (repo padre).
> **Decisión:** `../decisions/2026-09-24_escala-fija-potencia-activa.md` (D1–D5 aprobadas el 2026-09-24).
> **Estado:** aprobada · implementada en esta sesión (2026-09-24).

## 1. Objetivo y Contexto

**Objetivo:** que los dos históricos de potencia informen una **potencia de referencia** estable
para fijar el eje Y del frontend, en el header `X-Potencia-Referencia-W`.

**Alcance:**
- Dispositivo: P99 de `potencia_activa_total_W` en `[max(ahora - 30 d, datos_desde), ahora]`,
  independiente de `hours` y `hasta`.
- Nodo: P99 de la **serie sumada** de los medidores frontera en la misma ventana (D2). No sumar P99
  individuales.
- Header en `GET /api/v1/telemetria/instantaneous/{device_id}` y en
  `GET /api/v1/plantas/{planta_id}/unifilar/nodos/{nodo_id}/resumen/historico`. Agregarlo a
  `expose_headers`. Omitirlo si no hay datos suficientes.
- Caché del valor (se pide en cada carga y en cada ◀ ▶). La estrategia (SQL, agregados de 1 min,
  TTL) la define la hija.

**Fuera de alcance:** cambiar el cuerpo de las respuestas; `potencia_contratada_kw`.

**Certezas verificadas en este repo (rutas, callers, qué borrar):**
- Routers: `src/infrastructure/fastapi/routes/telemetria_router.py:69` y
  `planta_estructura_router.py:86`; helper del header: `src/infrastructure/fastapi/headers_historico.py`.
- CORS: `src/infrastructure/fastapi/server.py:461` (`expose_headers=[HEADER_DATOS_DESDE]`).
- Casos de uso: `consultar_telemetria.py:161` (`historico_instantaneas`) y
  `consultar_nodo_unifilar.py:254` (`historico`).
- Nada que borrar.

### 1.1 Certezas agregadas por la sesión hija (2026-09-24)

- `calcular_historico(ids, consultar, "5m", 720)` (`agregacion_dispositivos.py`) ya produce la serie
  que dibuja el frontend: bucketiza a 5 min, promedia cada medidor por bucket y suma entre medidores
  (`AgregadorDispositivosService.sumar_potencia_en_el_tiempo`). Con un solo id es la serie del
  medidor. 720 h es exactamente el máximo de `hours` y el límite se dimensiona a la ventana (8641
  buckets), así que 30 d llegan completos.
- Las lecturas se persisten cada 300 s (throttle de ingesta, ver `navegacion-temporal-telemetria.md`
  §1.1): a 5 min, un bucket ≈ una lectura. El P99 de la serie de 5 min es, en la práctica, el P99 de
  las lecturas persistidas.
- `listar_instantaneas` ya acota `desde` por el corte de retención del dispositivo; para el nodo el
  corte es `calcular_datos_desde` (máximo de los cortes), igual que en `historico`.
- MySQL no tiene `PERCENTILE_CONT`: el percentil se calcula en Python.
- **El intervalo mínimo del plan sube la serie:** `listar_instantaneas` usa
  `max(intervalo pedido, min_intervalo)`, y en plan free `min_intervalo` es 3600 s. Verificado con la
  DB local (solo lectura): un medidor con 3390 lecturas en ~12 días devuelve 284 puntos horarios.
  La referencia sale de la misma serie que dibuja el gráfico, así que en free es el P99 de promedios
  horarios. Todos los medidores de un nodo son de la misma organización (mismo plan), así que no
  se mezclan series de 5 min y de 1 h en una suma.

### 1.2 Decisiones de esta sesión (delegadas por la spec)

- **Mínimo de datos: 24 horas distintas con al menos un punto con potencia** (dentro de la ventana
  de 30 d acotada por la retención). Con menos se omite el header (el frontend conserva su
  comportamiento actual). Motivo: un medidor recién instalado fijaría la escala con un día atípico
  (la puesta en marcha). Se cuentan horas y no puntos por la certeza anterior: "288 puntos de 5 min"
  serían 24 h en PRO pero 12 días en free.
- **Percentil:** `statistics.quantiles(n=100, method="inclusive")[98]` (interpolación lineal, el
  método por defecto de NumPy). Se usa la potencia **con signo**, como la dibuja el gráfico.
- **Buckets parciales del nodo** (algún medidor sin dato): se incluyen. Subestiman la suma, así que
  no pueden inflar el P99; excluirlos dejaría al nodo sin referencia si un medidor está caído semanas.
- **Caché: en memoria por proceso, TTL 15 min**, clave `("dispositivo", device_id)` o
  `("nodo", org_id, planta_id, nodo_id)`. Cachea también `None`. Motivo: el P99 de 30 días casi no
  cambia en minutos, y el cálculo (≈ 8640 lecturas por medidor) no justifica una tabla de agregados
  ni una migración. Con varios workers cada uno calcula el suyo (a lo sumo una vez cada 15 min por
  medidor). Vive en infraestructura (`headers_historico.py`), no en el caso de uso: es un detalle de
  transporte, y los casos de uso se instancian por request.
- **Seguridad de la caché del nodo:** el router consulta la referencia **después** de `historico`,
  que valida el acceso a la planta; un usuario sin acceso recibe el 404/403 antes de tocar la caché.
  El `org_id` va igual en la clave. El dispositivo ya pasa por `verificar_propiedad_dispositivo`.
- **Robustez:** si el cálculo falla, se loguea `potencia_referencia_fallida` (warning) y se omite
  el header; el histórico responde igual (es un metadato opcional).
- **Formato:** W con un decimal (`"48123.5"`).

### 1.3 Prueba de humo contra la DB local (solo lectura, 2026-09-24)

- Con la retención real (7 d, corte 17-09) y datos locales hasta el 13-09, los 5 medidores dan
  `None`: el header se omitiría, como corresponde.
- Forzando el corte al 01-09 solo en el script: P99 por medidor 2 950 W, 521 863 W, 299 193 W,
  385 264 W y 192 364 W; P99 de la serie sumada de los 5: **1 230 443 W**, contra 1 401 635 W de
  sumar los P99 (+14 %): D2 confirmado con datos reales.
- Tiempo: 0,2–0,6 s por medidor y 1,6 s para 5 medidores sumados (primer pedido tras vencer el TTL).

### 1.4 Dudas (a validar)

- Con nodos de muchos medidores el primer pedido tras vencer la caché puede pasar de 2 s. Si se
  nota, pasar a un cálculo en SQL por buckets o precalcular en segundo plano; hoy no se justifica.
  Logs de producción (2026-09-24, 6 h): un solo proceso uvicorn y los nodos consultados tienen como
  máximo 2 medidores. Para medirlo, cada cálculo (solo al vencer la caché) registra
  `potencia_referencia_calculada` con `duracion_ms`, `muestras` y `referencia_w`.

## 2. Dominio & Puertos

- Nuevo `src/domain/telemetria/servicios/potencia_referencia.py` (solo stdlib):
  `VENTANA_REFERENCIA_HORAS = 720`, `GRANULARIDAD_REFERENCIA = "5m"`,
  `MINIMO_HORAS_CON_DATOS = 24`, `percentil_99(valores) -> float` y
  `potencia_referencia(muestras: list[tuple[datetime, float]], minimo_horas) -> float | None`.
- Sin cambios de puertos, entidades, modelo ni migraciones (no se toca el ERD).

## 3. Casos de Uso & DTOs

- `agregacion_dispositivos.calcular_potencia_referencia(ids, consultar) -> float | None`:
  `calcular_historico(ids, consultar, "5m", 720)` sin `hasta`, descarta puntos con
  `momento < calcular_datos_desde(ids)` o sin potencia, y devuelve `potencia_referencia`. `None` sin ids.
- `ConsultarNodoUnifilarUseCase.potencia_referencia(planta_id, nodo_id, organizacion_id)`: resuelve
  la frontera con `_resolver_nodo` y llama a `calcular_potencia_referencia`.
- DTOs sin cambios (el body no cambia).
- Infraestructura: `headers_historico.py` suma `HEADER_POTENCIA_REFERENCIA`, `CacheTTL`,
  `cache_potencia_referencia` y `setear_potencia_referencia(response, clave, calcular)`. Los dos
  routers la llaman; `server.py` agrega el header a `expose_headers`.

## 4. Matriz de Pruebas (RED Suite)

Archivo nuevo `tests/unit/test_potencia_referencia.py`; ajustes en `test_planta_estructura_router.py`
(mock de `potencia_referencia`, CORS) y `tests/unit/conftest.py` (limpia la caché entre tests).

```gherkin
Escenario 1: percentil_99 interpola (1..100 → 99.01); potencia_referencia exige 24 horas con
  datos, contadas igual con puntos de 5 min que de 1 h (23 h → None, 24 h → valor)
Escenario 2 (D2): dos medidores con picos de 1000 W no simultáneos → P99 de cada uno 1000,
  P99 de la suma 1000 (no 2000)
Escenario 3: la ventana es fija: horas=720, granularidad 5m, hasta=None, desde ≈ ahora - 30 d
Escenario 4: los puntos anteriores al corte de retención no cuentan
Escenario 5: sin datos suficientes o sin dispositivos → None
Escenario 6: el nodo calcula con los device_id de su frontera (ignora nodos sin medidor)
Escenario 7: CacheTTL reusa el valor (incluido None) dentro del TTL y recalcula al vencer
Escenario 8: routers — mismo header para ?hours=24 y ?hours=24&hasta=<hace 7 d>, calculado una
  sola vez; sin datos → header ausente; cálculo que falla → 200 sin header; nodo sin acceso → 404
  sin consultar la referencia; CORS expone X-Potencia-Referencia-W
```

## 5. Criterios del Gauntlet

- `./scripts/pre-push.sh` verde: integridad (`__init__.py` 0 bytes, headers de ruta relativa,
  ≤ 500 líneas por archivo de `src/`, ≤ 75 por método), `ruff check .`, `ruff format --check .`,
  `pyright` 0 errores, tests unitarios con cobertura ≥ 85 %.
- `scripts/verify_architecture.py`: el servicio nuevo de `domain/` solo importa stdlib.
- Tests de integración existentes (`test_telemetria_api.py`) verdes.
- Sin cambios de migraciones (`REVISION_HEAD` intacto) ni de `docs/database_erd.md`.
- Verificación en producción (post-deploy, la hace el dueño): `curl -i` a los dos endpoints con
  `?hours=24` y con `?hours=24&hasta=<hace 7 días>` muestra el mismo `X-Potencia-Referencia-W`.
