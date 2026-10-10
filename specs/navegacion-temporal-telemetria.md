# Navegación temporal (◀ ▶ "Ahora"): `hasta` y `datos_desde` en los históricos de potencia

> **Origen:** bloque `## Repo: datamaq-telemetry` de `../specs/navegacion-temporal-telemetria.md` (repo padre).
> **Decisión:** `../decisions/2026-09-23_navegacion-temporal-telemetria.md` (D1–D5 aprobadas el 2026-09-23).
> **Estado:** aprobada · implementada en esta sesión (2026-09-24).

## 1. Objetivo y Contexto

**Objetivo:** que los dos históricos de potencia acepten un `hasta` opcional, para consultar
ventanas del pasado sin cambiar el comportamiento cuando no se envía.

**Alcance:**
- Parámetro `hasta: FechaHoraUTC | None` en `get_instantaneous_history` y en `historico_nodo_unifilar`.
  La ventana es `[hasta - hours, hasta]`; sin `hasta`, `now`.
- Soportar `hasta` en el puerto `RepositorioTelemetriaPort.listar_instantaneas` y en su
  implementación SQLAlchemy (`recorded_at <= hasta`), o bien una variante nueva del puerto.
- Propagar `hasta` en `ConsultarTelemetriaUseCase.listar_instantaneas` → `calcular_historico` →
  `ConsultarNodoUnifilarUseCase.historico`.
- `_mezclar_buffer_en_vivo`: aplicarlo solo si `hasta` es `None` o está dentro del último intervalo (D4).
- `datos_desde` en la respuesta de los dos históricos (D3): en el dispositivo, su corte
  (`_calcular_fecha_corte_retencion`); en el nodo, el **máximo** de los cortes de sus dispositivos
  frontera, y los puntos anteriores a esa fecha no se devuelven. Ventana entera antes del corte:
  datos vacíos, no un error. La forma exacta (objeto con `datos_desde` o header) y la estrategia de
  despliegue (coordinado o versionado) las decide esta sesión y las documenta en su spec.
- Truncamiento en ventanas largas (ver certezas): asegurar que una ventana de 7 d llegue completa.
- Validar `hours` en el router del nodo con el mismo rango que el del dispositivo (`ge=1, le=720`);
  hoy no tiene validación.

**Fuera de alcance:** cambios de modelo o de migraciones; exportación CSV (ya tiene `desde`/`hasta`).

**Certezas verificadas en este repo (rutas, callers, qué tocar):**
- El router del dispositivo calcula `desde = now - timedelta(hours=hours)` en el propio router
  (`telemetria_router.py:85`). Con `hasta` pasa a ser `hasta - hours`.
- `SqlAlchemyTelemetriaRepository.listar_instantaneas` (`telemetria_repository.py:257`): filtra solo
  por `desde`, ordena `desc` y aplica `limit`.
- Hay un precedente de filtro con `hasta`: `iterar_instantaneas` en el mismo archivo (`:266`).
- `_acotar_fecha_desde` / `_calcular_fecha_corte_retencion` en `consultar_telemetria.py` ya recortan
  `desde`. El corte sale de tres fuentes (plan → `retencion_dias`; suscripción sin plan → días
  PRO/free; sin suscripción → 14 días) y se calcula **por dispositivo**.
- **Truncamiento confirmado:** `calcular_historico` (`agregacion_dispositivos.py`) pide
  `limite=2000` por dispositivo. Para 7 d a 5 min son 2016 intervalos, y como
  `agregar_lecturas_en_intervalo` (`agregador_lecturas.py:223`) ordena de más nuevo a más viejo
  antes del `[:limite]`, se pierden los ~16 intervalos (~80 min) **más antiguos** de la semana.
- Gotchas del repo: el hook de edición poda imports sin uso (agregar el import y su uso en la misma
  edición); límite de 75 líneas por método (`test_verify_code_size`); correr los tests con
  `.venv/bin/python -m pytest`.

### 1.1 Certezas agregadas por la sesión hija (2026-09-24)

- **Duda del tope de 20 000 lecturas crudas: RESUELTA, no es un problema.** El único camino que
  persiste lecturas instantáneas es `IngestarTelemetriaUseCase._procesar_instantanea`
  (`ingestar_telemetria.py:184`, único caller de `guardar_instantanea`), con un throttle por
  dispositivo de `granularidad_segundos = 300` (default; `mqtt_listener.py:186` no lo sobreescribe).
  El capturador de campañas escribe en otra tabla (no en `telemetry_instantaneous`). Verificado
  empíricamente con un `SELECT` de solo lectura sobre la DB local (`DB_HOST=127.0.0.1`, datos del
  2026-09-01 al 13): intervalo medio entre lecturas de 297,8–300,1 s en los 5 dispositivos, máximo
  15 lecturas/hora. Una semana son ≈ 2016 lecturas crudas y el máximo de `hours` (720 h) son ≈ 8640:
  muy por debajo de `max(limite × 10, 5000)`. El truncamiento real es el `limite=2000` **agregado**.
- **El histórico del nodo hoy ignora `hours` como ventana:** `calcular_historico` llama a
  `listar_instantaneas` sin `desde`, así que `desde_efectivo` cae al corte de retención y la ventana
  real es "hasta 2000 intervalos desde el corte" (≈ 7 d a 5 min), no las últimas `hours`. El frontend
  poda por su cuenta. Con `hasta` esto deja de ser tolerable (una ventana del pasado tiene que tener
  su inicio), así que `calcular_historico` pasa a calcular `desde = (hasta or now) - horas`.
- `calcular_historico` tiene otros dos callers: `_calcular_compensacion_historica` (nodo MT/total,
  `periodo_dias` = 30 por default) y `ConsultarAnaliticaPlantaUseCase.obtener_banco_capacitores`
  (7–60 d). Hoy los dos reciben, de hecho, ≈ 7 d aunque pidan 30. Con el límite dimensionado a la
  ventana reciben el período que declaran (acotado por la retención). Es una corrección, no una
  regresión, pero sube la carga: 30 d a 5 min = 8640 puntos por medidor.
- Implementadores de `RepositorioTelemetriaPort.listar_instantaneas`: SQLAlchemy y tres fakes de
  tests (`test_use_cases.py`, `test_optimizacion_db.py`, `test_buffer_en_vivo_endpoint.py`). El
  `iterar_instantaneas` por defecto del puerto ignora `hasta` al delegar (filtra en memoria después
  de truncar): se corrige para pasarlo.
- CORS (`server.py:450-466`) no expone headers propios: hay que agregar `expose_headers`.

### 1.2 Decisiones de esta sesión (delegadas por D3)

- **Forma del contrato de `datos_desde`: header HTTP `X-Datos-Desde`** (ISO 8601 UTC, con `Z`), en
  los dos históricos. El body **no cambia** (sigue siendo la lista pelada de
  `LecturaInstantaneaDTO` / `PuntoPotenciaNodoUnifilarDTO`). En el nodo sin medidores frontera el
  header se omite (no hay retención que informar; los datos son siempre vacíos).
- **Estrategia de despliegue: ninguna coordinación ni versionado.** Con header, el cambio es
  estrictamente aditivo (`hasta` opcional + header nuevo): el backend se puede desplegar antes que
  el frontend y el frontend actual sigue funcionando. Motivo: el CD del backend despliega al
  pushear `main`, y un cambio de forma del body abriría una ventana de producción rota hasta el
  despliegue de `app-datamaq`. Se descartó versionar (`/api/v2`) porque no hay precedente en el
  repo y duplicaría dos endpoints por un solo campo.
- `CORSMiddleware` expone `X-Datos-Desde` (`expose_headers`) en las dos ramas (con y sin `*`); sin
  eso, `axios` no puede leerlo desde `app.datamaq.com.ar`.
- **Consecuencia para `app-datamaq`:** su bloque dice "adaptar los esquemas Zod a la nueva forma de
  respuesta con `datos_desde`". Con esta decisión, no cambia ningún esquema de body: el servicio
  lee `response.headers['x-datos-desde']` (axios normaliza a minúsculas). El padre debe actualizar
  esa línea y el "Contexto cruzado".
- **D4, "dentro del último intervalo":** se mezcla el buffer si `hasta is None` o
  `hasta >= now - max(intervalo_de_agregación, 300 s)` (300 s = throttle de persistencia: el buffer
  solo aporta lecturas todavía no persistidas). Al mezclar con `hasta`, se descartan las lecturas
  del buffer posteriores a `hasta`.
- **Filtro del nodo:** se descartan los puntos con `momento < datos_desde`. Un bucket que empieza
  antes del corte se descarta aunque tenga datos parciales (conservador: la suma nunca queda
  incompleta sin aviso).

### 1.3 Extensión (2026-09-24): `X-Datos-Desde` en energía

- `GET /api/v1/telemetria/energy/{device_id}` también acota `days` por el corte de retención
  (`_acotar_fecha_desde`) sin avisarlo en el body: el gráfico "Energía activa (últimos 30 días)"
  mostraba 7 días en una suscripción sin PRO. Ahora manda `X-Datos-Desde` con el mismo contrato de
  §1.2 (mismo corte, `ConsultarTelemetriaUseCase.datos_desde`), para las tres granularidades.
  Aditivo: body sin cambios, CORS ya lo expone. Origen: análisis del histograma de consumo
  (doc del padre, fila "se puede hacer ya").

## 2. Dominio & Puertos

- `RepositorioTelemetriaPort.listar_instantaneas(dispositivo_id, limite, desde=None, hasta=None)`:
  nuevo parámetro opcional `hasta` (`recorded_at <= hasta`, inclusivo). Sin `hasta` el
  comportamiento es idéntico. Se amplía el puerto existente en lugar de una variante nueva: el único
  llamador de producción es `ConsultarTelemetriaUseCase` y el parámetro es opcional.
- `iterar_instantaneas` (implementación por defecto del puerto): pasa `hasta` a `listar_instantaneas`.
- `SqlAlchemyTelemetriaRepository.listar_instantaneas`: agrega el filtro, igual que `iterar_instantaneas`.
- Sin cambios de entidades, value objects ni modelo/migraciones (no se toca el ERD).

## 3. Casos de Uso & DTOs

### 3.1 DTOs (application, no son `response_model`)

- `HistoricoInstantaneasDTO(lecturas: list[LecturaInstantaneaDTO], datos_desde: FechaHoraUTC)`
  en `telemetria_dto.py`.
- `HistoricoNodoUnifilarDTO(puntos: list[PuntoPotenciaNodoUnifilarDTO], datos_desde: FechaHoraUTC | None)`
  en `planta_estructura_dto.py`.

### 3.2 `ConsultarTelemetriaUseCase`

- `listar_instantaneas(..., hasta: datetime | None = None)`:
  - `horas_efectivas` sin `horas` se calcula como `(hasta or now) - desde`.
  - Si `hasta < desde_efectivo` (ventana entera antes del corte): devuelve `[]` sin consultar la BD.
  - Pasa `hasta` al repositorio.
  - `_mezclar_buffer_en_vivo(dev_id, dtos, limite, hasta, intervalo_segundos)` según §1.2 (D4).
- `datos_desde(id_o_uid) -> datetime`: el corte de retención del dispositivo (público; lo usa
  `calcular_historico` para el nodo).
- `historico_instantaneas(id_o_uid, limite, desde, granularidad, horas, hasta) -> HistoricoInstantaneasDTO`:
  orquesta `listar_instantaneas` + `datos_desde` para el router.

### 3.3 `agregacion_dispositivos`

- `calcular_historico(ids, consultar, granularidad, horas, hasta=None)`:
  `desde = (hasta or now) - horas`; `limite = max(2000, ceil(horas·3600 / intervalo) + 1)`; pasa
  `desde`, `hasta`. Firma compatible con los tres callers existentes.
- `calcular_datos_desde(ids, consultar) -> datetime | None`: máximo de `consultar.datos_desde(id)`;
  `None` si no hay ids.

### 3.4 `ConsultarNodoUnifilarUseCase.historico(..., hasta=None) -> HistoricoNodoUnifilarDTO`

- Calcula `datos_desde` con `calcular_datos_desde`, obtiene los puntos con `calcular_historico(..., hasta)`
  y descarta los de `momento < datos_desde`.

### 3.5 Routers

- `GET /api/v1/telemetria/instantaneous/{device_id}`: nuevo `hasta: FechaHoraUTC | None = Query(None)`.
  `desde = (hasta or now) - hours` si hay `hours`. Llama a `historico_instantaneas`, setea
  `X-Datos-Desde` y devuelve `lecturas` (el `response_model` no cambia).
- `GET /api/v1/plantas/{planta_id}/unifilar/nodos/{nodo_id}/resumen/historico`: `hours: int = Query(24, ge=1, le=720)`,
  nuevo `hasta`. Setea `X-Datos-Desde` si no es `None` y devuelve `puntos`.
- `server.py`: `expose_headers=["X-Datos-Desde"]` en los dos `CORSMiddleware`.

## 4. Matriz de Pruebas (RED Suite)

Archivo nuevo: `tests/unit/test_navegacion_temporal.py` (use cases + agregación), más ajustes a
`test_telemetria_router.py`, `test_planta_estructura_router.py`, `test_consultar_nodo_unifilar.py`
y a los fakes del puerto.

```gherkin
Escenario 1: hasta acota la ventana del dispositivo por arriba
  Dado un fake de repositorio con lecturas a t0, t0+1h, t0+2h (raw)
  Cuando listar_instantaneas(granularidad="raw", desde=t0, hasta=t0+1h)
  Entonces solo vuelven las lecturas de t0 y t0+1h

Escenario 2: ventana entera antes del corte de retención → lista vacía, sin error
  Dado un dispositivo sin suscripción (corte = now - 14 d)
  Cuando pido hasta = now - 20 d y horas = 1
  Entonces la lista es vacía y no se consulta el repositorio

Escenario 3: buffer en vivo no se mezcla en una ventana del pasado (D4)
  Dado un buffer con una lectura de "ahora"
  Cuando pido hasta = now - 2 h
  Entonces la lectura del buffer no aparece

Escenario 4: buffer en vivo se mezcla si hasta cae en el último intervalo, sin lecturas posteriores a hasta
  Dado un buffer con lecturas a now-60 s y now-10 s
  Cuando pido hasta = now - 30 s
  Entonces aparece la de now-60 s y no la de now-10 s

Escenario 5: historico_instantaneas informa datos_desde = corte del dispositivo
  Dado un dispositivo sin suscripción
  Entonces datos_desde ≈ now - 14 d

Escenario 6: calcular_historico dimensiona el límite y pasa la ventana
  Cuando calcular_historico(horas=168, granularidad="5m", hasta=H)
  Entonces cada llamada a listar_instantaneas recibe limite ≥ 2017, desde = H - 168 h y hasta = H

Escenario 7: 7 d a 5 min llega completa (regresión del truncamiento)
  Dado un fake con una lectura cada 300 s durante 7 d
  Cuando el nodo pide horas=168
  Entonces el primer punto es del inicio de la semana (no se pierden los ~80 min más viejos)

Escenario 8: nodo — datos_desde es el máximo de los cortes y filtra puntos anteriores
  Dado dos medidores frontera con cortes C1 < C2
  Entonces datos_desde = C2 y ningún punto tiene momento < C2

Escenario 9: nodo sin medidores frontera → datos_desde None, header ausente

Escenario 10: routers
  - instantaneous con hasta: desde = hasta - hours, hasta se propaga, header X-Datos-Desde presente
  - instantaneous sin hasta: comportamiento previo (desde ≈ now - hours) y header presente
  - nodo: hours=0 y hours=721 → 422; hasta se propaga; header presente
  - CORS: X-Datos-Desde en Access-Control-Expose-Headers

Escenario 11: repositorio SQLAlchemy filtra recorded_at <= hasta
  (unitario con sesión mockeada, como el resto de `test_telemetria_repository.py`: no hay
  fixture SQLite en el repo)
```

## 5. Criterios del Gauntlet

- `./scripts/pre-push.sh`: integridad (`__init__.py` 0 bytes, headers de ruta relativa, tamaño:
  ≤ 500 líneas por archivo de `src/`, ≤ 75 por método), `ruff check .`, `ruff format --check .`,
  `pyright` 0 errores, tests unitarios con cobertura ≥ 85 %.
- `.venv/bin/python scripts/verify_architecture.py`: `domain/` solo stdlib.
- Tests de integración existentes (`test_buffer_en_vivo_endpoint.py`, `test_telemetria_api.py`) verdes.
- Sin cambios de migraciones (`REVISION_HEAD` intacto) ni de `docs/database_erd.md`.
