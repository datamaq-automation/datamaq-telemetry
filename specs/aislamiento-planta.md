# Aislamiento por planta en las rutas que reciben `planta_id` (IDOR, OWASP A01)

## 1. Objetivo y Contexto

Origen: `app-datamaq/docs/delegacion-backend-aislamiento-planta.md` (2026-09-24). La SPA va a poner
el id de la planta en la URL (`/plantas/:plantaId/...`); antes de desplegarlo hay que cerrar un
control de acceso roto: un usuario de la organización A que conozca el id de una planta de B lee su
topología, áreas, layout, líneas de base y analítica.

Auditoría en `d98a80a` (lectura del código, no suposición):

| Ruta | Recibe claims | Verificaba acceso a la planta |
| :--- | :--- | :--- |
| `GET /api/v1/plantas/{planta_id}/unifilar` | No | **No** |
| `GET /api/v1/plantas/{planta_id}/areas` | No | **No** |
| `GET /api/v1/plantas/{planta_id}/layout` | No | **No** |
| `GET /api/v1/planta/unifilar?planta_id=` | Sí | **No** (`_resolver_planta` ignora la org si llega id) |
| `GET /api/v1/planta/areas?planta_id=` | Sí | **No** (ídem) |
| `GET /api/v1/planta/layout?planta_id=` | Sí | **No** (ídem) |
| `GET /api/v1/plantas/{planta_id}/unifilar/nodos/{nodo_id}/resumen` | Sí | Parcial: solo organización (`ConsultarNodoUnifilarUseCase._resolver_planta`), sin `user_facility_access` |
| `GET .../unifilar/nodos/{nodo_id}/resumen/historico` | Sí | Parcial (ídem) |
| `GET /api/v1/plantas/{planta_id}/balance-energia` | Sí, sin usar | **No** |
| `GET /api/v1/plantas/{planta_id}/ahorros-cusum` | Sí, sin usar | **No** |
| `GET /api/v1/plantas/{planta_id}/linea-base` | Sí, sin usar | **No** |
| `GET /api/v1/analitica/banco-capacitores/planta?planta_id=` | Sí, sin usar | **No** (no estaba en la delegación) |
| `GET /api/v1/analitica/penalizaciones/planta?planta_id=` | Sí, sin usar | **No** (no estaba en la delegación) |

Hallazgo adicional: las rutas **sin** `planta_id` (`/planta/unifilar|layout|areas`) usan como
"planta activa" `listar_plantas(org)[0]`. Para un usuario con asignaciones en `user_facility_access`
eso puede ser una planta **no** asignada (fuga intra-organización), y para un usuario sin
organización `listar_plantas(None)[0]` es la primera planta de **todo** el YAML (fuga
inter-organización). Además no coincide con `planta_activa_id` de `/auth/me`, que la SPA usa como
destino por defecto.

**Alcance:**
- Una única dependencia FastAPI que resuelve la planta efectiva contra
  `PoliticaAccesoPlantasService.resolver` (vía `GestionarAccesoPlantasUseCase.resolver`, la misma
  fuente que `/auth/me`) y responde **404** si la planta no está permitida o no existe.
- Aplicarla a todas las rutas de la tabla.
- Unificar la planta activa: sin `planta_id`, las rutas por defecto usan la primera planta
  permitida (idéntica a `planta_activa_id` de `/auth/me`). `GestionarPlantaEstructuraUseCase`
  deja de elegir planta por su cuenta.
- Defensa en profundidad: `GestionarPlantaEstructuraUseCase._resolver_planta` verifica la
  organización cuando la recibe (como ya hace `ConsultarNodoUnifilarUseCase`).

**Fuera de alcance (registrado):**
- `GET /api/v1/plantas` no aplica `user_facility_access` (solo organización). Lo consume también la
  administración de usuarios para asignar plantas; restringirlo sin revisar ese flujo en la SPA
  podría impedir que un admin con asignaciones vea las plantas a asignar. Expone solo nombres de
  plantas de la propia organización.
- El aislamiento por dispositivo (`verificar_propiedad_dispositivo`, `GET /dispositivos?planta_id=`)
  es por organización, no por planta asignada. Un usuario restringido a la planta X puede leer
  telemetría de un medidor de la planta Y de su misma organización si conoce su id.

## 2. Dominio & Puertos

Sin cambios en `domain/`: la regla ya existe en `PoliticaAccesoPlantasService.resolver`
(`src/domain/auth/services.py`). No se crean puertos ni entidades.

## 3. Caso de uso & DTOs

- `GestionarAccesoPlantasUseCase.resolver_planta_permitida(usuario_id, rol, organizacion_id,
  planta_id) -> str | None`:
  - `planta_id` presente y dentro de `resolver(...)` → devuelve `planta_id`.
  - `planta_id` presente y fuera (ajena, no asignada o inexistente) → `PlantaNoEncontradaError`.
  - `planta_id` ausente → `planta_activa(resolver(...))` (puede ser `None`).
- `GestionarPlantaEstructuraUseCase._resolver_planta(planta_id, organizacion_id)`:
  - sin `planta_id` → `None` (el caller devuelve el DTO vacío, Empty State 200);
  - con `planta_id` → planta del repo; `PlantaNoEncontradaError` si no existe o si
    `organizacion_id` no es `None` y no coincide.
- Dependencia `resolver_planta_permitida` en `src/infrastructure/fastapi/planta_ownership.py`:
  - parámetro `planta_id: str | None = None` (FastAPI lo toma del path o de la query según la ruta);
  - `AUTH_REQUIRED=False` → se resuelve como rol global (comportamiento dev previo);
  - si no, `usuario_id = claims["sub"]`, `rol = claims["rol"]`, `organizacion_id = claims["org"]`;
  - `PlantaNoEncontradaError` → `HTTPException(404, "planta_no_encontrada")`, mismo detalle para
    ajena e inexistente.
- Rutas: `Depends(resolver_planta_permitida)`; las de `planta_estructura_router` usan el valor
  devuelto como planta efectiva y pasan la organización al caso de uso.

## 4. Matriz de Pruebas (RED Suite)

Unitarias del caso de uso (`tests/unit/test_acceso_plantas.py`):
- planta propia permitida → devuelve id; planta de otra org → `PlantaNoEncontradaError`;
  inexistente → error; con asignaciones, planta no asignada de la propia org → error;
  superadmin / invitado_global → cualquier planta; sin id → primera permitida (orden de asignación).

API (`tests/unit/test_aislamiento_planta_api.py`, caso de uso real con repos en memoria, org A con
plantas `a1`, `a2`; org B con `b1`):
- usuario de A → 404 en `/plantas/b1/{unifilar,areas,layout}`, `/plantas/b1/unifilar/nodos/n/resumen`,
  `.../resumen/historico`, `/plantas/b1/{balance-energia,ahorros-cusum,linea-base}`,
  `/analitica/{banco-capacitores,penalizaciones}/planta?planta_id=b1`;
- usuario de A → 404 en `/planta/{unifilar,areas,layout}?planta_id=b1`;
- usuario de A asignado solo a `a1` → 404 en `/plantas/a2/unifilar`, y `/planta/unifilar` sin id
  devuelve `a1`;
- superadmin e invitado_global → 200 en `/plantas/b1/unifilar`;
- planta inexistente → 404 con el mismo detalle que la ajena.

## 5. Criterios del Gauntlet

- `venv/bin/ruff check .` y `venv/bin/ruff format --check .` sin errores.
- `venv/bin/python -m pyright` sin diagnósticos.
- `venv/bin/python -m pytest tests/unit -n auto` en verde, cobertura ≥ 85 %.
- `scripts/verify_architecture.py` y `scripts/verify_code_size.py` (ningún archivo de `src/` > 500 líneas).
- `./scripts/pre-push.sh` (etapas 1-4) exitoso.
