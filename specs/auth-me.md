# Spec — `GET /api/auth/me` (restauración de sesión con rol)

> **Documento:** `specs/auth-me.md`
> **Versión:** `1.0.0`
> **Estado:** `aprobado`
> **Fecha:** `2026-08-17`
> **Autor:** DataMaq — equipo `datamaq-telemetry`
> **Referencia:** `spec.md` §4.2; `app-datamaq/specs/auth-sesion-rol.md` (D-01); `app-datamaq/docs/delegacion-backend-auth.md` (D-01)

---

## 1. Objetivo y Contexto

La cookie de sesión `datamaq_token` es `HttpOnly` (ilegible por JS). Al recargar la SPA,
no hay forma de recuperar el nombre de usuario real ni el rol desde los claims del JWT sin
un endpoint dedicado. Hoy el frontend sondea un endpoint protegido y restaura el último
usuario conocido desde `sessionStorage`, lo que puede desincronizarse.

**Objetivo:** exponer `GET /api/auth/me` que devuelve `{usuario, rol}` leídos de los claims
del JWT ya validado por `get_usuario_actual`, para que la SPA restaure la sesión de forma
desacoplada.

**Fuera de alcance:** D-02 (`Retry-After` en 429), D-03 (`X-Request-ID` en ≥500), D-04
(guest), D-04b (scoping por rol), D-05 (`POST /api/usuarios`).

**Dependencias:** `get_usuario_actual` (`src/infrastructure/fastapi/dependencies.py`) ya
valida cookie/Bearer y devuelve los claims `{sub, usuario, rol, exp, iat}` o lanza `401
credenciales_invalidas`. No se modifica el dominio: se reutiliza `CredencialesInvalidasError`
(`domain/auth/exceptions.py`), ya mapeado a `401` por `ErrorPresenter`.

---

## 2. Contrato (HTTP)

| Aspecto | Valor |
| :-- | :-- |
| Método/Ruta | `GET /api/auth/me` |
| Autenticación | `get_usuario_actual` (cookie `datamaq_token` o `Authorization: Bearer`) |
| `200` | `{"usuario": str, "rol": "admin"\|"operador"\|"invitado"}` |
| `401` | `{"detail": "credenciales_invalidas"}` (sin token, token inválido o claims incompletos) |

**Caso dev (`AUTH_REQUIRED=False`):** `get_usuario_actual` cortocircuita y devuelve
`{"sub": "anon", "rol": "admin"}` (sin claim `usuario`). `GET /api/auth/me` responde
`200 {"usuario": "anon", "rol": "admin"}` (fallback `sub`).

**Reglas de validación de claims:**

- `rol` ausente o fuera de `{"admin", "operador", "invitado"}` → `401` (`CredencialesInvalidasError`).
- `usuario` ausente → fallback `sub` (y si tampoco existe, `"anon"`).

---

## 3. Casos de Uso y DTOs

### `src/application/dtos/auth_dto.py`

- `MeResponseDTO(BaseModel)`: `usuario: str`, `rol: Literal["admin", "operador", "invitado"]`.

### `src/application/use_cases/autenticar_usuario.py`

- `AutenticarUsuarioUseCase.me(claims: dict[str, Any]) -> MeResponseDTO`:
  - Extrae `rol = claims.get("rol")`; si no está en el conjunto válido (`ROLES_VALIDOS`) → `CredencialesInvalidasError`.
  - Extrae `usuario = claims.get("usuario") or claims.get("sub") or "anon"`.
  - Devuelve `MeResponseDTO(usuario=usuario, rol=rol)`.
  - Agnóstico de framework web (sin imports de FastAPI).

### `src/infrastructure/fastapi/routes/auth_router.py`

- `@router.get("/me", response_model=MeResponseDTO)`:
  - `def me(claims: Annotated[dict[str, Any], Depends(get_usuario_actual)], use_case: Annotated[AutenticarUsuarioUseCase, Depends(get_auth_use_case)]) -> MeResponseDTO`
  - `try/except Exception → manejar_error_http(e)`.

---

## 4. Matriz de Pruebas (RED Suite)

### `tests/unit/test_auth.py`

| # | Escenario |
| :-- | :-- |
| U1 | `me()` con claims `{usuario, rol="admin"}` → `MeResponseDTO(usuario, "admin")`. |
| U2 | `me()` con `rol="operador"` / `"invitado"` → DTO con el rol correspondiente. |
| U3 | `me()` con `rol` ausente o inválido (`"superadmin"`) → `CredencialesInvalidasError`. |
| U4 | `me()` con claims sin `usuario` (`{sub: "anon", rol: "admin"}`) → `usuario="anon"`. |
| U5 | `me()` con `usuario` y `sub` ausentes → `usuario="anon"`. |
| U6 | handler `auth_router.me` con claims válidos → `MeResponseDTO`. |
| U7 | handler `auth_router.me` con `rol` inválido → `HTTPException(401)`. |

### `tests/integration/test_auth_api.py`

| # | Escenario |
| :-- | :-- |
| I1 | `create_app()` expone `GET /api/auth/me`. |
| I2 | La ruta `/api/auth/me` está protegida por `get_usuario_actual`. |

---

## 5. Criterios del Gauntlet

```bash
./scripts/pre-push.sh    # etapas 1-4 (integridad, ruff, pyright, unit >=85%)
./scripts/ci.sh          # incluye integración
```

Sin relajar tests. Prohibido `# type: ignore`, `cast(Any, ...)`, `@pytest.mark.skip`.
