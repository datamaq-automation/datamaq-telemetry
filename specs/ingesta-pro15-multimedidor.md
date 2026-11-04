# Spec: Ingesta del Powermeter Pro15 — multimedidor (repo `datamaq-telemetry`)

> **Estado:** en implementación (parser puro listo) · **Issue:** datamaq-automation/datamaq#151
> **Origen:** `specs/ingesta-pro15-multimedidor.md` del repo padre (bloque `Repo: datamaq-telemetry`).
> **Rama:** `feat/issue-151-ingesta-pro15`, desde `develop`.
> **Traspasada a hija:** sí · **Bloque cerrado:** no (falta identidad por medidor, despacho y validación con datos reales).

## 1. Objetivo y Contexto

**Objetivo:** ingerir el Pro15 con cada medidor interno como una serie de medición independiente, sin afectar la ingesta de los equipos `m/wifi/#`.

**Alcance:**
- Parseo de topics `pro15/{MAC}/{sub}/v1` y de payloads en lista por medidor, con fases por posición.
- Identidad por par (MAC, `id` de medidor). Debe funcionar con Trafo 1 (`id:0`) y Trafo 2 (`id:1`) sin pisarse.
- Lectura de `model` y `fw` del `device_info` del Pro15.
- Pruebas con los mensajes reales de la captura del 2026-11-03 como casos, sin broker real.
- Corrección de `docs/provisioning_guide.md` (usuarios y claves del broker).

**Fuera de alcance:** el ACL del VPS (DevOps), la configuración del equipo, agregar `pro15/#` a la configuración de producción y activar en producción antes de resolver la validez de la medición.

## 2. Dominio & Puertos

Hecho en `src/domain/telemetria/servicios/pro15_payload.py` (stdlib, puro, sin excepciones que escapen):

- `parsear_topico_pro15(topico) -> TopicPro15 | None`. Valida la **forma completa** `pro15/{MAC}/{sub}/v1` con `sub` en `{inst, acc, energyio, thd, onoff, status}` y MAC de 12 hex. Así `pro15/inst/v1` no se toma como MAC (la trampa de `IngestarTelemetriaUseCase.ejecutar`, que usa `partes[2]`).
- `bloques_por_subtopico(sub, payload) -> list[BloquePro15]`. Cada `BloquePro15` tiene `medidor_id` (el `id` del mensaje), `timestamp` (`t`) y `datos` ya en el formato que entienden los parsers existentes:
  - `inst` → `{"f": [{"n": R|S|T, "v","i","p","q"}]}` → `parse_fase`.
  - `acc` → `{"f": [{"n","a": kWh, "r": kVARh}]}` → `EnergiaPayloadParser`.
  - `energyio` → `{"total": {imported_active_energy_KWH, …}}` → `EnergiaPayloadParser`.
  - `thd` → `{"f": [{"n": 0|1|2, "THDv","THDi"}]}` → `parsear_thd_harmonics`.
  - `onoff`, `status` → sin conversor (`[]`).
- Las fases se asignan **por posición** (0→R, 1→S, 2→T). Entradas no dict se reemplazan por `{}`; `id` no entero o booleano se descarta; valores no numéricos quedan en `None`.

**Puertos:** sin cambios en esta entrega.

**Pendiente (requiere decisión, ver §3):** persistencia de la identidad (MAC, `id`).

## 3. Casos de Uso & DTOs

**Modelo de identidad (Opción A, aprobada técnicamente por el padre el 2026-11-03; implementada en código, no ejecutada):**

- Hoy `devices.device_uid` es `String(64) UNIQUE` (`src/infrastructure/sqlalchemy/models.py`) y `MacAddress` acepta solo 12 hex. Una MAC es un dispositivo, así que los dos trafos se pisarían.
- Opción A (**recomendada**): nueva columna `medidor_id` (entero, nullable; `NULL` para todos los equipos actuales) y restricción única `(device_uid, medidor_id)` en lugar de `device_uid` única. Los dos trafos son dos filas con la misma MAC y `medidor_id` 0 y 1. El `device_uid` queda igual, así que los equipos `m/wifi/#` no cambian.
- Opción B: `device_uid` sintético por medidor (`{MAC}-1`). Requiere relajar `MacAddress`, que es valor de dominio, y rompe búsquedas por MAC en `dispositivos_datos_maestros_gateway`, `device_ownership` y el `verificador_consistencia`. Descartada.

**Migración (Opción A):** requiere una revisión Alembic nueva. `tests/unit/test_migraciones.py::REVISION_HEAD` debe actualizarse. **No se aplica en ninguna base real** sin autorización del dueño: se describe en el reporte al padre antes de ejecutarla. En la base de desarrollo se prueba con SQLite/fixtures.

**Despacho (pendiente):** en `MQTTListener._ejecutar_ingesta`, los tópicos `pro15/…` van a un caso de uso nuevo `IngestarPro15UseCase` (patrón de `IngestarAutomateUseCase`), igual que `auto24v4m/`. Por cada bloque: resuelve dispositivo (MAC, `medidor_id`), y reusa `IngestarTelemetriaUseCase` para `inst`/`acc`/`energyio`/`thd` con el bloque convertido. `onoff`/`status` van a su manejo existente (heartbeat / log de estado).

**Modelo del `device_info` (pendiente):** el resolvedor lee `device_model` y `hw_model` (`resolvedor_dispositivo.py`), pero el Pro15 manda `model` y `fw`. Hay que mapear `model`→`modelo` y `fw`→`version_fw`. Sin ese cambio el equipo se registra como `SmartPlus`.

**Propiedad y organización por medidor (decisión del padre, 2026-11-03):** cada medidor se resuelve por su fila `(device_uid, medidor_id)`. No se hereda de la MAC. El esquema lo permite: la fila trae `facility_id`, y el repositorio resuelve `(uid, medidor)` con `one_or_none`. Lo que falta no es de esquema sino de exposición:

- **Medidor 1 no es direccionable por MAC.** Las rutas y casos de uso que reciben solo una MAC (`device_ownership`, `consultar_telemetria`, `gestionar_dispositivos` x2, `ingestar_automate`, `resolver_organizacion_id`) resuelven el medidor 0 por default. Un medidor 1 solo se alcanza por su `id` interno.
- **Pendiente de API:** exponer el `id` del medidor (o `MAC/medidor`) en las rutas. Bloquea activar la ingesta del Pro15 en producción, **no** el desarrollo.
- **Deuda de tests:** ~20 fakes de `RepositorioDispositivosPort` tienen la firma `obtener_por_uid(self, uid)`. Se actualizan a `(self, uid, medidor_id=0)` cuando se habilite la ejecución de tests.

**Garantía de no regresión:** el despacho de `m/wifi/#` y `auto24v4m/#` no cambia. `pro15/` se evalúa antes del caso genérico solo por prefijo exacto.

## 4. Matriz de Pruebas

| Caso | Dónde | Estado |
|---|---|---|
| Topic válido extrae MAC y subtópico | `tests/unit/test_pro15_payload.py` | ✅ |
| `pro15/inst/v1` y `pro15/{MAC}/inst` no son válidos (no se confunde con MAC) | ídem | ✅ |
| Subtópico desconocido, MAC inválida, `m/wifi/…` no son Pro15 | ídem | ✅ |
| `inst` separa `id` 0 y 1, fases R,S,T por posición, reactiva negativa intacta | ídem (fixture real) | ✅ |
| `acc` convierte kWh/kVARh a `a`/`r` | ídem | ✅ |
| `energyio` convierte `kWhi`… a claves del parser de energía | ídem | ✅ |
| `thd` pasa por `parsear_thd_harmonics` (1,88 %, 5,69 %) | ídem | ✅ |
| `onoff`/`status` no producen bloques | ídem | ✅ |
| Payload malformado no lanza | ídem | ✅ |
| Identidad (MAC, `medidor_id`): dos trafos no se pisan | — | ⏳ depende de la decisión de migración |
| Despacho `pro15/…` a la ingesta sin tocar `m/wifi/#` | — | ⏳ |
| `device_info.model`/`fw` se registran correctamente | — | ⏳ |
| Migración Alembic + `REVISION_HEAD` | — | ⏳ (no aplicar en base real) |

## 5. Criterios del Gauntlet

- Gauntlet local verde antes de cada push: `APP_ENV=test ./scripts/pre-push.sh`.
- Sin broker, sin base real, sin `.env` de producción. Los tests usan `tests/fixtures/pro15_mensajes_reales.json` (copia literal de la captura del 2026-11-03).
- `m/wifi/#` y `auto24v4m/#` sin cambios de comportamiento: sus tests existentes siguen verdes.
- Commits atómicos: dominio (`feat(dominio)`), aplicación (`feat(aplicacion)`), infraestructura (`feat(infra)`), docs (`docs(...)`).

## 6. Dependencias y riesgos

- **Validez de la medición (del padre):** bloquea activar en producción, no el desarrollo. Ver el repo padre.
- **ACL del broker (DevOps):** `datamaq-backend` debe tener lectura sobre `pro15/#` antes de activar la ingesta. Esta sesión no toca el ACL.
- **Migración (decisión pendiente):** la Opción A requiere autorización del dueño antes de aplicarla en cualquier base real.
- **Documentación:** `docs/provisioning_guide.md` dice que `MQTT_PASSWORD` del `.env` es la clave de `datamaq_device`, pero hoy es la de `datamaq-backend`. Corrección pendiente en esta rama.
