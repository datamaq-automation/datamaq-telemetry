> **⚠️ Desactualizado (2026-10-15).** Este documento describe tres roles y rutas sin `/v1`. El estado vigente está en `specs/roles-y-permisos.md` y en la matriz generada `docs/matriz-roles-permisos.md`.

# Spec R: Permisos por rol — invitado de solo lectura (D-04b)

## 1. Objetivo y Contexto

Acotar el rol `invitado` (emitido por `POST /api/auth/guest`) a **solo lectura**
en los routers protegidos. Hoy todas las rutas protegidas usan únicamente
`get_usuario_actual` (solo autenticación, sin distinción de rol); el único guard
por rol existente es `requiere_rol_admin` en `POST /api/system/purge`.

**Decisiones aprobadas:**

- **D-04b:** el rol `invitado` puede leer (GET) telemetría, dispositivos,
  organizaciones, plantas, planes y alertas, pero **no** puede ejecutar
  operaciones de escritura. `admin` y `operador` conservan acceso completo.
- **Mecanismo:** nueva dependencia `requiere_rol_escritura` (rechaza `invitado`
  con `403 {"detail": "forbidden"}`, mismo formato que `requiere_rol_admin`).
- **Alcance:** no se filtra por organización (multi-tenant es trabajo futuro,
  consistente con DEC-02).

## 2. Matriz de permisos por endpoint

| Endpoint | invitado | operador | admin |
|---|---|---|---|
| `GET /api/telemetria/*` | ✅ | ✅ | ✅ |
| `GET /api/dispositivos`, `GET /api/dispositivos/{id}` | ✅ | ✅ | ✅ |
| `POST /api/dispositivos`, `PUT /api/dispositivos/{id}` | ❌ 403 | ✅ | ✅ |
| `GET /api/organizaciones`, `GET /api/plantas` | ✅ | ✅ | ✅ |
| `POST /api/organizaciones`, `POST /api/plantas` | ❌ 403 | ✅ | ✅ |
| `GET /api/planes` | ✅ | ✅ | ✅ |
| `POST /api/planes` | ❌ 403 | ✅ | ✅ |
| `GET /api/alertas` | ✅ | ✅ | ✅ |
| `POST /api/alertas/{id}/resolver` | ❌ 403 | ✅ | ✅ |
| `POST /api/system/purge` | ❌ 403 | ❌ 403 | ✅ |

## 3. Adaptadores e Infraestructura

- `src/infrastructure/fastapi/dependencies.py` — nueva dependencia:
  `requiere_rol_escritura(claims)` → `403 forbidden` si `claims.get("rol") ==
  "invitado"`; si no, devuelve `claims`.
- Routers: aplicar `dependencies=[Depends(requiere_rol_escritura)]` en los
  endpoints de escritura:
  - `dispositivos_router.py` — `POST ""`, `PUT "/{device_id}"`.
  - `organizaciones_router.py` — `POST "/organizaciones"`, `POST "/plantas"`.
  - `planes_router.py` — `POST "/planes"`.
  - `alertas_router.py` — `POST "/{alerta_id}/resolver"`.
  - Los GET y `telemetria_router` no cambian; `system_router` ya usa
    `requiere_rol_admin`.

## 4. Matriz de Pruebas (RED Suite)

### `tests/unit/test_permisos_rol.py`

1. `test_requiere_rol_escritura_rechaza_invitado` — `HTTPException 403
   forbidden` con `{"rol": "invitado"}`.
2. `test_requiere_rol_escritura_acepta_admin_y_operador` — devuelve claims.
3. `test_endpoints_escritura_exigen_rol_escritura` — las rutas POST/PUT de
   dispositivos, organizaciones, planes y alertas incluyen la dependencia.
4. `test_endpoints_lectura_no_exigen_rol_escritura` — ninguna ruta GET la incluye.
5. `test_requiere_rol_admin_rechaza_invitado` — purge rechaza invitado (403).

## 5. Criterios del Gauntlet

```bash
bash scripts/pre-push.sh   # integridad, ruff, pyright, tests unitarios >=85%
bash scripts/ci.sh         # + integración
```

`__init__.py` de 0 bytes. Sin cambios en `domain/`. Cobertura de
`requiere_rol_escritura` y del cableado de routers cubierta por la suite unitaria.
