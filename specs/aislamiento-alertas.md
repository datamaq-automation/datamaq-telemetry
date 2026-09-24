# Aislamiento por organización en `/api/v1/alertas` (IDOR, OWASP A01)

## 1. Objetivo y Contexto

Detectado el 2026-09-24 al aislar el asistente (`specs/bot-conversacional-aislamiento.md`); el dueño
aprobó corregirlo como iniciativa propia.

Auditoría de todo lo que expone alertas, en `3f49758`:

| Superficie | Verificaba acceso |
| :--- | :--- |
| `GET /api/v1/alertas` (`alertas_router.list_alertas`) | **No**: no recibe claims ni pasa organización; devuelve alertas de todos los clientes. Con `?device_id=` tampoco verifica la propiedad del dispositivo |
| `POST\|PATCH /api/v1/alertas/{alerta_id}/resolver` | **No**: cualquier rol de escritura resuelve alertas de otra organización (y el evento se difunde por WS) |
| `GET /api/v1/telemetria/alerts/{device_id}` | Sí (`verificar_propiedad_dispositivo`) |
| WebSocket `/ws/live`, tópico `m/wifi/{mac}/alertas` | Sí (`debe_recibir_evento`) |

Uso: la SPA consume las dos rutas abiertas (`app-datamaq/src/core/services/telemetry.ts:218,225`).
Nginx no registró llamadas a `/api/v1/alertas` entre el 14/09 y el 24/09.

**Alcance:**
- Listado: rol global (`superadmin`, `invitado_global`) → todas; resto → solo las de su organización
  (claim `org`); sin `org` → lista vacía (fail-closed, igual que `GET /dispositivos`). Un
  `device_id` ajeno devuelve lista vacía por el mismo filtro.
- Resolución: dependencia `verificar_propiedad_alerta` (patrón `verificar_propiedad_evento_disponibilidad`):
  alerta ajena o inexistente → 404 `alerta_no_encontrada`.

**Fuera de alcance (registrado):** el aislamiento por planta asignada (`user_facility_access`) de
alertas y telemetría por dispositivo. Hoy todo el acceso por dispositivo es por organización; se
resuelve junto con esa deuda, no acá.

## 2. Dominio & Puertos

Sin cambios de dominio: se reutilizan `debe_recibir_evento` y el filtro `organizacion_id` que
`RepositorioTelemetriaPort.listar_alertas` ya acepta desde `af7c73b`
(alerta → `devices` → `facilities.organization_id`).

## 3. Caso de uso & DTOs

- `alertas_router.list_alertas` recibe los claims y pasa `organizacion_id` a
  `GestionarAlertasUseCase.listar_alertas` (roles globales → `None`; sin `org` → `[]` sin consultar).
- `device_ownership.verificar_propiedad_alerta(claims, db, alerta_id)`: sin auth o rol global pasa;
  si no, alerta → dispositivo → planta → organización (YAML, como el resto de `device_ownership`);
  distinta u irresoluble → `HTTPException(404, "alerta_no_encontrada")`.
- Las dos rutas de resolución agregan `Depends(verificar_propiedad_alerta)` después de
  `requiere_rol_escritura` (los invitados siguen recibiendo 403).

## 4. Matriz de Pruebas (RED Suite)

`tests/unit/test_aislamiento_alertas.py`, repositorios reales sobre SQLite (org A y org B con planta,
medidor y alerta):
- usuario de A lista → solo la alerta de A; con `device_id` de B → `[]`;
- superadmin / invitado_global → las dos;
- usuario sin `org` → `[]`;
- usuario de A resuelve la alerta de B (POST y PATCH) → 404 y la alerta sigue abierta;
- usuario de A resuelve la suya → 200; alerta inexistente → 404.

## 5. Criterios del Gauntlet

- `venv/bin/ruff check .`, `venv/bin/ruff format --check .`, `venv/bin/python -m pyright` sin errores.
- `venv/bin/python -m pytest tests/unit -n auto --cov=src --cov-fail-under=85` en verde, también con
  `DB_HOST=127.0.0.2 DB_PORT=1` (como en CI).
- `scripts/verify_architecture.py` y `scripts/verify_code_size.py`.
