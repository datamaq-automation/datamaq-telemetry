# ADR-001 · No incorporar Redis como capa de cache sobre MySQL

> **Estado:** Aceptado
> **Fecha:** 2026-09-13
> **Decisores:** Dirección de Ingeniería (backend `datamaq-telemetry`)
> **Revisar cuando:** se cumpla alguno de los disparadores de la sección 5.

---

## 1. Contexto

Surgió la pregunta de si conviene "implementar Redis para optimizar la base de datos".
Antes de decidir se midió el estado real de producción (VPS `vps4`, base `datamaq_telemetry`,
lectura de `information_schema` y `SHOW GLOBAL STATUS`, uptime de 6,2 días):

| Métrica | Valor medido | Interpretación |
|---|---|---|
| Dispositivos activos / organizaciones / usuarios | 4 / 3 / 6 | Carga de laboratorio, no de escala |
| Ingesta `telemetry_instantaneous` | ≈ 520 filas/día (≈ 1 cada 3 min por medidor) | Trivial para InnoDB |
| Tabla más grande (`telemetry_energy`) | 422 209 filas · 78,8 MB (12 días de datos) | Entra 3 veces en el buffer pool **hoy**; a ≈ 6,6 MB/día deja de entrar en ~40 días |
| `innodb_buffer_pool_size` | 256 MB | — |
| Buffer pool hit ratio | 1 − 2 091 / 304 367 184 = **99,9993 %** | La base ya reside en RAM (propiedad de una tabla joven; ver nota de particionado) |
| Throughput | 3 938 659 queries / 538 345 s ≈ **7,3 q/s** | 6 conexiones concurrentes |
| `Slow_queries` | 38 en 6 días | Sin cuello de botella identificable |
| Servidor | 2 vCPU · 3,9 GB RAM · ≈ 1 GB disponible | RAM es el recurso escaso |
| Procesos backend | 1 worker uvicorn por puerto (8003 / 8885) | Todo el estado volátil es in-process |

El código no tiene hoy ninguna capa de cache de datos: solo `functools.lru_cache(maxsize=1)`
para singletons de configuración y sesión (`config.py`, `database.py`, `dependencies.py`).
Los índices compuestos `idx_telemetry_*_dev_time (device_id, recorded_at)` cubren el patrón
de consulta del dashboard (`WHERE device_id = ? AND recorded_at BETWEEN ? AND ?`).

## 2. Decisión

**No se incorpora Redis.** Ni como cache de lectura sobre MySQL ni como dependencia "por si
acaso". La optimización de la base, si alguna vez hace falta, se aborda primero con medición
(`slow_query_log`), `EXPLAIN` e índices/particionado, no con una capa adicional de estado.

## 3. Fundamento

1. **No hay problema que resolver.** Un cache evita lecturas caras y repetidas. Con hit ratio
   99,999 % y 7 q/s, la latencia de MySQL en memoria es indistinguible de la de Redis en memoria
   más un salto de red local. La ganancia medible es cero.
2. **Cuesta el recurso que más escasea.** Redis es un segundo sistema stateful en una máquina con
   ≈ 1 GB libre. La RAM que consuma es RAM que no recibe el buffer pool de InnoDB, que es lo que
   hoy hace que la base sea rápida.
3. **Introduce una clase nueva de errores.** Un cache de entidades exige invalidación explícita.
   Ejemplo concreto del día anterior: el `UPDATE` sobre `devices.phases_with_ct` del medidor de
   invitado (D-16) habría requerido invalidar la clave de ese dispositivo, o la SPA habría seguido
   viendo `R,S,T`. Hoy ese riesgo no existe porque la única fuente de verdad es MySQL.
4. **Los índices ya están.** El patrón de acceso principal ya está cubierto. Si un histórico se
   vuelve lento, el primer paso es `EXPLAIN` sobre esa consulta.

## 4. Alternativas consideradas

| Alternativa | Veredicto |
|---|---|
| Redis como cache read-through de `GET /dispositivos` y `/telemetria/latest` | Rechazada: ganancia nula, costo en RAM e invalidación. |
| Redis para pub/sub del WebSocket `inst` | Innecesaria con un solo worker; ver disparadores. |
| Redis para el `rate_limiter` de login/recuperación | Innecesaria con un solo worker; ver disparadores. |
| Aumentar `innodb_buffer_pool_size` | No hace falta: la base entera ya cabe con margen. |
| Particionado mensual de `telemetry_energy` | Diferido: es la única tabla que crece, y crece rápido (≈ 35 000 filas/día, 6,6 MB/día, ≈ 2,4 GB/año con 5 medidores; la tabla tenía 12 días al medir, por eso cabía en el buffer pool). Es la primera medida cuando supere ~1 GB, junto con ejecutar la purga por retención, que hoy existe pero nada programa. Sigue sin ser un caso para Redis: es volumen de escritura, no latencia de lectura. |

## 5. Disparadores para revisar esta decisión

Redis (o equivalente) pasa a estar justificado cuando aparezca una necesidad de **coordinación
entre procesos**, que es distinta de "velocidad de lectura":

- **Más de un worker de uvicorn** en `datamaq-telemetry` (como ya hace `datamaq-hub` con
  `--workers 2`). En ese escenario el `rate_limiter` (`autenticar_usuario.py`,
  `recuperar_contrasena.py`) cuenta intentos por proceso y se vuelve inconsistente, y el fan-out
  del WebSocket `inst` no alcanza a clientes conectados a otro worker. Redis (contadores + pub/sub)
  es la herramienta correcta ahí.
- **Más de una instancia del backend** (segundo VPS, o separar el consumer MQTT del API HTTP).
- **Colas de trabajo diferido** (evaluación de alertas, downsampling) si la ingesta llegara a
  bloquear el request path. A 520 filas/día no lo hace.

Si el disparador es **crecimiento de ingesta** (p. ej. 400 medidores a 1 s), el cuello será de
**escritura**, y la respuesta es batch inserts / particionado / motor de series temporales,
tampoco Redis.

## 6. Consecuencias

- Se mantiene una sola fuente de verdad (MySQL) y un solo proceso por servicio; cero
  invalidación de cache que razonar.
- Cualquier futuro trabajo de "rendimiento de base" empieza por activar
  `slow_query_log` (`long_query_time = 1`) y por `performance_schema`, no por agregar
  infraestructura. La primera revisión con `performance_schema` (2026-09-13) ya identificó
  mejoras concretas que no requieren Redis: agregación de energía en SQL en lugar de cargar la
  serie cruda (`listar_acumulados_para_agregacion`, hasta 41 s), filas duplicadas por ingesta
  doble `acc`/`energyio` sin `UNIQUE(device_id, recorded_at)`, y purga por retención sin programar.
- Este ADR se revisa al primer disparador de la sección 5, con nuevas mediciones, no antes.
