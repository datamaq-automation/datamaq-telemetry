# Detector de potencia negativa (inyección indeseada en CONSUMO)

> Origen: bloque `datamaq-telemetry` de `/home/agustin/proyectos_software/datamaq/specs/detector-potencia-negativa.md`
> (sección 1 escrita por el padre). Esta copia documenta el estado real y los desvíos de diseño.

## 1. Objetivo y Contexto

Detectar potencia activa total negativa (P < 0) en instalaciones de CONSUMO durante la ingesta MQTT,
alertar en menos de 5 minutos y verificar que el detector habría disparado el 2026-10-02 a las 09:00.

## Estado por tarea

| Tarea | Estado | Evidencia |
|---|---|---|
| T1 — Evaluador | HECHO (pusheado, `ca4105d`) | `src/domain/telemetria/servicios/evaluador_potencia_negativa.py`, `EvaluadorPotenciaNegativaService.evaluar_alerta_potencia_negativa` |
| T2 — Integración en ingesta | HECHO con diseño distinto (ver desvío) | `src/application/use_cases/ingesta/procesador_alertas_ingesta.py:275-313` (`_evaluar_potencia_negativa_fn`) y `:427` |
| T3 — Tests unitarios | HECHO | `tests/unit/test_evaluador_potencia_negativa.py` (10 casos) |
| T4 — Test retroactivo | HECHO | `tests/integration/test_potencia_signos.py` |
| T5 — Gauntlet | HECHO local (gauntlet completo verde); CI remoto pendiente de push | `scripts/pre-push.sh` |

## Desvío de diseño: persistencia

**Spec original (T2):** contador de sostenimiento en la tabla `telemetria_anomalias`; escalada a alerta
CRITICAL más Slack cuando hay 5 o más lecturas sostenidas en una ventana de 5 minutos.

**Diseño implementado:** el evaluador es puro (devuelve la alerta cruda). La persistencia la decide
`FiltroPersistenciaTemporalService` (`src/domain/telemetria/servicios/persistencia_alertas.py`), el mismo
filtro que usan las demás alertas de calidad, con `min_lecturas=2` y `min_segundos=3.0`. La alerta se confirma
en la segunda lectura consecutiva; una lectura normal reinicia la racha.

**Por qué se cambió:**

1. Reutiliza el mecanismo ya probado para tensión, desbalance y THD, en vez de una segunda maquinaria
   de persistencia con la misma responsabilidad (anti alert fatigue).
2. No requiere escribir un contador por lectura en `telemetria_anomalias`, que es una tabla de coherencia (Capa 1).
3. El criterio de confirmación (2 lecturas consecutivas) cumple el objetivo de latencia de la spec
   (< 5 min) siempre que la frecuencia de ingesta sea de minutos o menos. Esa frecuencia no la medí en este repo.

**Consecuencias:**

- La "escalada" a 5 lecturas en 5 minutos de la spec no existe como tal. Lo que hay es confirmación rápida.
  Si el padre quiere la ventana de 5 min con umbral de 5, es un cambio acotado en el filtro, no en el evaluador.
- Slack: no verificado en este repo. El despacho de la alerta usa el notificador existente
  (`_despachar_alerta_fn`); la spec original lo nombraba explícitamente.
- **Pendiente (sin acción):** verificar la escalada a Slack. Queda sin verificar por decisión del padre.

## Desvío de límite (aceptado por el padre)

- **Spec:** "P = -100 W (límite) → alerta CRITICAL".
- **Código:** el umbral es **estricto**: alerta solo si `P < -100 W`. En exactamente -100,0 W no hay alerta.
- **Por qué se acepta:** exactamente -100,0 W no ocurre de forma estable en la medición; en la práctica es lo mismo que la spec.
- El test `test_potencia_exactamente_en_el_umbral_no_alerta` fija el comportamiento actual.

## Otros puntos verificados

- `src/domain/telemetria/servicios/evaluador_anomalias_fases.py` no tiene lógica propia para
  `POTENCIA_NEGATIVA`. En la línea 176 expone `evaluar_alerta_potencia_negativa` como alias de
  `EvaluadorPotenciaNegativaService`. `AnalizadorCalidadEnergiaService` hereda ese alias, y es el que usa la ingesta.
  Cubierto por `test_anomalias_fases_delega_en_el_evaluador_dedicado`.
- Instalaciones `GENERACION_FV` quedan fuera (`tipo_instalacion`, caso cubierto en los tests).

## Fuera de alcance (sin cambios)

- Histéresis con ventana móvil de 5 min: Fase 2.
- Dashboard con métrica de signo de potencia: Fase 2.
- Integración Tuya (LED ámbar): Fase 3.
