# Pico falso de 22 811 kW: suma de lecturas en la tool MCP y días que absorben huecos

> **Issue:** datamaq-automation/datamaq#18 · **Rama:** `fix/issue-18-mcp-suma-lecturas`

## 1. Objetivo y Contexto

Durax mostró un "pico de 22 811 kW". Los datos crudos tienen como máximo 574 kW. La hipótesis inicial fue un delta de
energía de 19 780 kWh (el 14/09, después de 41,5 h sin datos) dividido por un intervalo corto.

**Lo que se encontró en el código:** ningún cálculo del backend, del frontend ni del MCP deriva kW de deltas de kWh. La
demanda de 15 min, los históricos, la potencia de referencia y las penalizaciones salen de potencia instantánea. El
número sale de la tool MCP `datamaq_consultar_potencia_reciente`:

- Pide `GET /telemetria/instantaneous/{id}?granularity=5m` por medidor. Ese endpoint antepone las lecturas crudas del
  buffer en vivo (`_mezclar_buffer_en_vivo`), una cada pocos segundos con el modo tiempo real activo, que caen todas en
  el último bucket de 5 min.
- `_agregar_serie_planta` **sumaba todas las lecturas del bucket, aunque fueran del mismo medidor**: 40 × 570,28 kW =
  22 811,2 kW, que salía como `potencia_activa_max_kw`. Q se sumaba igual, así que el FP vectorial del bucket también
  quedaba distorsionado.
- Es el mismo bug que `40d9dda` (2026-09-23) corrigió en `AgregadorDispositivosService` del backend; el MCP tiene su
  propia agregación y no recibió el fix.

El salto de 19 780 kWh es real (consumo acumulado durante el hueco), pero la barra diaria del 14/09 lo atribuye a un
solo día.

## 2. Dominio & Puertos

- `EnergiaAgregada.periodos_sin_datos_previos: int = 0`: periodos completos sin ningún acumulado entre el anterior con
  dato y este. N = 1 periodo (día o mes, según la granularidad).
- `AgregacionEnergiaService._periodos_entre(anterior, actual, granularidad)`.
- `AgregadorDispositivosService.sumar_energia_agregada`: la suma de un nodo toma el máximo de sus medidores.

## 3. Caso de uso & DTOs

- `tools/mcp/server.py`: `_promedios_por_bucket` promedia P y Q de **un** medidor por bucket; `_agregar_serie_planta`
  suma esos promedios entre medidores. `metodo` del resultado: "promedio por dispositivo y suma entre dispositivos, por
  bucket de 5 min".
- `EnergiaAgregadaDTO.periodos_sin_datos_previos` (aditivo, default 0) en la energía del dispositivo y en el resumen de
  nodo. Propagado en `agregacion_dispositivos.calcular_resumen`.

**Límite conocido:** el repositorio devuelve un acumulado por periodo (el último, con `ROW_NUMBER()` en SQL), así que un
hueco que no cubre un periodo entero (por ejemplo, 20 h que cruzan la medianoche) no se detecta.

## 4. Matriz de Pruebas (RED Suite)

| Archivo | Test |
|---|---|
| `tools/mcp/test_server.py` | 1 lectura agregada + 40 crudas de 570,28 kW del mismo medidor → máx 570,28 (antes **22 811,2**, el número de Durax) |
| | 2 medidores con 40 y 1 lecturas en el bucket → 150 + 50 = 200 kW (antes 6 050) |
| | P solo en un medidor (40 lecturas) y Q solo en otro (1) → FP 0,707 (antes ~1,0) |
| `tests/unit/test_agregacion_energia.py` | caso Durax: 14/09 = 19 780,5 kWh con `periodos_sin_datos_previos=1`; días consecutivos = 0; meses con 1 y 2 sin datos; suma de nodo propaga el máximo |
| `tests/unit/test_energia_agregada_dto.py` | el DTO expone el campo; default 0 |

## 5. Criterios del Gauntlet

`./scripts/pre-push.sh` en verde con `APP_ENV=test`. `tools/` está fuera del `include` de pyright: los 4 errores de
`round()` en `tools/mcp/server.py` (l. 402-404) ya estaban en `main` y no son de este cambio.

## 6. Notas de implementación

- El frontend (`app-datamaq`) puede usar `periodos_sin_datos_previos > 0` para avisar en la barra ("incluye N días sin
  datos"). No es parte de esta rama.
- Por qué aparecía solo a veces: depende de que haya un WebSocket conectado (modo tiempo real) y de cuántas lecturas
  crudas caigan en el último bucket al momento de la consulta.
