# Spec — Eliminación de la capa `adapters/controllers` (Lean / KISS)

> **Documento:** `specs/eliminar-capa-controllers.md`
> **Versión:** `1.0.0`
> **Estado:** `aprobado`
> **Fecha:** `2026-08-17`
> **Autor:** DataMaq — equipo `datamaq-telemetry`
> **Referencia:** auditoría de sobreingeniería; `spec.md` Spec C (principio "cero sobreingeniería").

---

## 1. Objetivo y Contexto

La auditoría de sobreingeniería detectó que la capa `src/adapters/controllers/`
(6 archivos) es **indirección sin valor**: los controllers son passthrough puro
que delegan al caso de uso (`return self.use_case.X(...)`) sin lógica propia,
salvo `AuthController.me()` (validación de rol en claims + construcción de
`MeResponseDTO`). Los instancia únicamente `dependencies.py` y los consumen solo
los routers de FastAPI vía `Depends(get_X_controller)`.

**Objetivo:** eliminar `src/adapters/controllers/` por completo y que los routers
inyecten los casos de uso directamente (`Depends(get_X_use_case)`), trasladando la
única lógica real (`AuthController.me`) a `AutenticarUsuarioUseCase.me(claims)`.

**Se preservan** (vivos y usados, verificados por evidencia directa):
- `src/adapters/gateways/` — `InMemoryEventBroadcaster` (pipeline MQTT → WebSocket `/ws/live`).
- `src/adapters/presenters/` — `ErrorPresenter` (usado por `error_handler.py` + tests + specs).
- `src/application/mappers/` — `TelemetriaMapper`, `DispositivoMapper`, `PlanMapper`, `AlertaMapper`.

**Fuera de alcance:** cualquier cambio de comportamiento HTTP, de dominio, de
DTOs, de mappers o de infraestructura de persistencia/MQTT. Cero cambios en los 20
endpoints expuestos.

---

## 2. Cambios de Firma

### `src/application/use_cases/autenticar_usuario.py`

- `AutenticarUsuarioUseCase.me(claims: dict[str, Any]) -> MeResponseDTO`:
  - `ROLES_VALIDOS = frozenset({"admin", "operador", "invitado"})` (constante de módulo).
  - `rol = claims.get("rol")`; si no está en `ROLES_VALIDOS` → `CredencialesInvalidasError("Rol inválido en los claims del token.")`.
  - `usuario = str(claims.get("usuario") or claims.get("sub") or "anon")`.
  - Devuelve `MeResponseDTO(usuario=usuario, rol=rol)`.
  - Agnóstico de framework web (sin imports de FastAPI), igual que el resto del use case.

### `src/infrastructure/fastapi/dependencies.py`

Renombrar y cambiar el tipo de retorno (la construcción interna no cambia):

| Antes | Después |
| :-- | :-- |
| `get_telemetria_controller(...) -> TelemetriaController` | `get_telemetria_use_case(...) -> ConsultarTelemetriaUseCase` |
| `get_dispositivos_controller(...) -> DispositivosController` | `get_dispositivos_use_case(...) -> GestionarDispositivosUseCase` |
| `get_planes_controller(...) -> PlanesController` | `get_planes_use_case(...) -> GestionarPlanesUseCase` |
| `get_purga_controller(...) -> PurgaController` | `get_purga_use_case(...) -> PurgarTelemetriaExpiradaUseCase` |
| `get_alertas_controller(...) -> AlertasController` | `get_alertas_use_case(...) -> GestionarAlertasUseCase` |
| `get_auth_controller(...) -> AuthController` | `get_auth_use_case(...) -> AutenticarUsuarioUseCase` |

> Nota: `get_telemetria_controller` ensamblaba dos use cases (`consultar_uc`,
> `ingestar_uc`), pero el `ingestar_uc` solo lo consume el MQTT listener (que lo
> construye por su cuenta en `mqtt_listener.py`). El getter nuevo devuelve
> únicamente `ConsultarTelemetriaUseCase`, eliminando el código muerto del
> `ingestar_uc` en el contexto HTTP.

### Routers (`src/infrastructure/fastapi/routes/`)

Sustituir inyección `controller: Annotated[XController, Depends(get_X_controller)]`
→ `use_case: Annotated[XUseCase, Depends(get_X_use_case)]` y llamadas
`controller.metodo(...)` → `use_case.metodo(...)`. Afecta:

- `auth_router.py` — `login`, `guest`, `me` (4 handlers).
- `dispositivos_router.py` — 4 endpoints.
- `organizaciones_router.py` — 4 endpoints.
- `telemetria_router.py` — 3 endpoints (`latest`, `instantaneous`, `energy`).
- `planes_router.py` — 2 endpoints.
- `alertas_router.py` — 2 endpoints.
- `system_router.py` — 1 endpoint (`purge`).

---

## 3. Archivos Eliminados

```
src/adapters/controllers/__init__.py
src/adapters/controllers/auth_controller.py
src/adapters/controllers/dispositivos_controller.py
src/adapters/controllers/planes_controller.py
src/adapters/controllers/purga_controller.py
src/adapters/controllers/alertas_controller.py
src/adapters/controllers/telemetria_controller.py
```

La carpeta `src/adapters/controllers/` queda vacía y se elimina. La regla de
arquitectura de `scripts/verify_architecture.py` para `src/adapters/` sigue
cubriendo `gateways/` y `presenters/` sin cambios.

---

## 4. Matriz de Pruebas (RED Suite)

### `tests/unit/test_auth.py`

| # | Escenario | Cambio |
| :-- | :-- | :-- |
| C1 | `use_case.me({usuario, rol="admin"})` → `MeResponseDTO(usuario, "admin")` | `_controller_me()` → `_use_case_me()` que devuelve el use case; tests U1-U5 usan `use_case.me(...)` |
| C2 | `me()` con `rol` ausente/inválido → `CredencialesInvalidasError` | idem (U3) |
| C3 | `me()` con claims sin `usuario` (`{sub:"anon"}`) → `usuario="anon"` | idem (U4-U5) |
| C4 | `login_handler`/`me_handler` reciben **use case** inyectado | los 6 tests de `login_handler` + 2 de `me_handler` pasan `use_case` en lugar de `controller` |
| C5 | assertions intactas | no se relaja ni borra ningún assert |

### `tests/unit/test_guest_endpoint.py`

| # | Escenario | Cambio |
| :-- | :-- | :-- |
| C6 | `guest_handler` recibe **use case** | `_controller()` → `_use_case_guest()`; tests G2-G3 pasan `use_case` |
| C7 | `test_me_con_token_guest` usa `use_case.me(claims)` | `_controller().me(claims)` → `_use_case_guest().me(claims)` |

### `tests/integration/*.py`

Sin cambios: no referencian `adapters/controllers` (verificado). Los 20 endpoints
mantienen firmas y `response_model` idénticos.

---

## 5. Criterios del Gauntlet

```bash
./scripts/pre-push.sh   # etapas 1-4 (integridad, ruff, pyright, unit >=85%)
./scripts/ci.sh         # + integración
```

Reglas inmutables: `__init__.py` de 0 bytes; prohibidos `# type: ignore`,
`# noqa`, `cast(Any, ...)`, `@pytest.mark.skip`; imports absolutos `from src...`.

Resultado esperado: −~230 líneas de indirección en `src/`, cobertura efectiva al
alza, comportamiento HTTP inalterado.
