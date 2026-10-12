# Alertas sin duplicados y estado OFFLINE por inactividad

> **Issue:** datamaq-automation/datamaq#19 · **Rama:** `fix/issue-19-alertas-dedup-offline`

## 1. Objetivo y Contexto

Diagnóstico de solo lectura en producción (2026-10-11):

- Durax tiene 127 `SOBRECOMPENSACION_REACTIVA` abiertas. Un medidor (`…BF2C`) acumula 116 abiertas a la vez del
  mismo tipo: cada detección abría una alerta nueva en vez de actualizar la que ya estaba abierta.
- Los medidores sin datos (Durax desde las 14:10 y Hogar desde las 18:40 del 11/10) siguen `ONLINE`.

**Fuera de alcance (decisión del dueño):** el texto del mensaje de acción y las alertas de los dispositivos
desactivados (SmartPlus #1, `F8B3B7C0BBB0`).

## 2. Dominio & Puertos

- `AlertaDispositivo.ultima_deteccion_en` y `ocurrencias` (default 1).
- `es_equivalente(otra)`: mismo dispositivo, tipo y fase. BAJA_TENSION en R y en S son alertas distintas.
- `registrar_reincidencia(nueva)`: conserva `disparada_en`, suma una ocurrencia y toma los valores, la severidad y el
  mensaje de la última detección.

Sin puertos nuevos: la búsqueda usa `RepositorioTelemetriaPort.listar_alertas(solo_abiertas=True)`.

## 3. Caso de uso & DTOs

**Deduplicación:** `_despachar_alerta_fn` (ingesta) busca la abierta equivalente (la más antigua, si ya hay
duplicadas) y le registra la reincidencia. Solo abre una nueva si no hay ninguna. La reincidencia se publica en vivo,
pero no se vuelve a notificar. `AlertaResponseDTO` expone `ultima_deteccion_en` y `ocurrencias` (aditivos).

**Persistencia:** migración `c4e8a1d2f6b9` (desde `7603c19a617f`): `device_alerts.last_detected_at` y `occurrences`
(`server_default 1`). El mapeo alerta → modelo pasa a `telemetria_mappers.alerta_a_modelo`, que usan los dos caminos de
`guardar_alerta`. `MySQLTelemetriaRepository` estaba en 509/510 líneas.

**Consolidación:** `scripts/consolidar_alertas_duplicadas.py`, idempotente, en dry-run salvo `--aplicar`. Por grupo
abierto de (dispositivo, tipo, fase) deja la más antigua con las ocurrencias sumadas, la última detección y los valores
de la más reciente, y resuelve las demás con "Consolidada en la alerta #id (#19)". Excluye los dispositivos
desactivados salvo `--incluir-inactivos`. **Correrlo en producción lo autoriza el dueño**:

```bash
.venv/bin/python -m scripts.consolidar_alertas_duplicadas            # informa
.venv/bin/python -m scripts.consolidar_alertas_duplicadas --aplicar  # escribe
```

**OFFLINE:** `MonitorearSaludDispositivosUseCase` existía desde `eccc85d` (2026-09-12) y ya marcaba OFFLINE, **pero
nada lo invocaba**. Ahora:

- `vigilancia_conectividad.loop_vigilancia_conectividad` lo corre cada 60 s en el lifespan de la API (en un hilo, con su
  propia sesión).
- `DISPOSITIVO_OFFLINE_TIMEOUT_S=900`: 3 × el intervalo normal de 300 s, para no oscilar con un mensaje demorado. El
  modo tiempo real publica más seguido y no cambia nada.
- `DISPOSITIVO_OFFLINE_ALERTA_HABILITADA=False`: con `False` solo marca OFFLINE, sin abrir `PÉRDIDA_COMUNICACIÓN`.
  `configurar_notificador` sigue sin llamarse: no salen emails.
- El monitor actualiza solo estado y última recepción (`actualizar_heartbeat`). `guardar` reescribía el dispositivo
  entero.
- **Vuelta a ONLINE:** la hace la ingesta. `ResolvedorDispositivoIngesta` llama a `marcar_online` y a
  `actualizar_heartbeat` cuando pasaron ≥ 60 s del último heartbeat, y eso siempre se cumple después de 900 s sin datos.
- **Workers:** supone un solo proceso, como el listener MQTT y `_loop_campanas_activas`
  (`systemd/datamaq-api.service`: `--workers 1`; ADR-001). Con más workers el bucle correría una vez por worker: marcar
  OFFLINE es idempotente, pero con la alerta habilitada podría abrirse por duplicado.

## 4. Matriz de Pruebas (RED Suite)

| Archivo | Tests |
|---|---|
| `test_alerta_reincidencia.py` | equivalencia por dispositivo, tipo y fase; la reincidencia conserva el inicio y actualiza |
| `test_alerta_mapeo_modelo.py` | ida y vuelta de `ultima_deteccion_en` y `ocurrencias`; una fila previa sin `occurrences` se lee como 1 |
| `test_alertas_dedup_ingesta.py` | 116 detecciones → 1 abierta con 116 ocurrencias; otro tipo u otra fase abren la suya; resuelta → abre otra; con duplicadas previas actualiza la más antigua; se publica con las ocurrencias. 4 de 5 fallan sin el cambio |
| `test_consolidar_alertas_duplicadas.py` | dry-run no escribe; consolida en la más antigua; idempotente; suma ocurrencias previas; no mezcla tipos ni fases; excluye inactivos; no toca resueltas |
| `test_dispositivo_offline_por_inactividad.py` | ciclo ONLINE→OFFLINE→ONLINE con la ingesta real; 600 s siguen ONLINE; alerta apagada no abre alerta y loguea; inactivo no se toca; no usa `guardar` |
| `test_vigilancia_conectividad.py` | toma el umbral y la alerta de Settings; defaults 900 y `False`; el bucle loguea el error y sigue; `server` usa el bucle |

## 5. Criterios del Gauntlet

`./scripts/pre-push.sh` en verde con `APP_ENV=test`. `REVISION_HEAD = "c4e8a1d2f6b9"` y `docs/database_erd.md`
regenerado.

## 6. Notas de implementación

- **Colisión de migraciones:** el checkout principal tiene, sin commitear, una migración de la línea #3
  (`crear_tabla_activos_unifilar`). Si también sale de `7603c19a617f`, quien mergee segundo tiene que rebasear su
  `down_revision` (registrado por el padre en `TODO.md`).
- **Al desplegar:** la migración corre en el deploy (`alembic upgrade head`). Las alertas duplicadas existentes
  quedan como están hasta que el dueño autorice correr el script de consolidación.
- Las alertas de evento del medidor (`IngestarTelemetriaUseCase._procesar_event`) no pasan por
  `_despachar_alerta_fn` y no se deduplican: no aparecieron en el diagnóstico.
