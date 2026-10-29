# Spec F: Usuario invitado (`invitado` / `invitado`)

> **⚠️ Superado.** Los roles `invitado` e `invitado_global` se retiraron de `develop` y `main` (PR #74; compatibilidad temporal en PR #76). El estado vigente de roles y permisos está en [`specs/roles-y-permisos.md`](roles-y-permisos.md) y en la matriz generada [`docs/matriz-roles-permisos.md`](../docs/matriz-roles-permisos.md). Este documento se conserva como histórico.

> **Estado:** Implementado (DEC-03) · **Nota de vigencia:** La SPA utiliza preferentemente el endpoint sin credenciales `POST /api/auth/guest` (DEC-04, ver `specs/guest-endpoint.md`, `specs/roles-permisos.md` y `docs/contrato-auth.md`). El seed de este documento se mantiene activo para scripts de prueba y retrocompatibilidad.

## 1. Objetivo y Contexto

Proveer un usuario de acceso rápido `invitado` con rol `invitado`, creado de forma
idempotente mediante un script de seed manual (sin endpoint de registro público,
consistente con la decisión de `specs/auth.md`).

**Decisiones aprobadas:**

- **Alcance de entornos:** seed manual, disponible en development y production. El
  operador decide ejecutarlo; el script advierte del riesgo de la contraseña
  débil por defecto.
- **Rol:** `invitado` (string libre; el claim `rol` ya viaja en el JWT generado
  por `JwtTokenService`). Hoy no existen guardas por rol, pero el claim queda
  disponible para restricciones futuras.
- **Contraseña:** se lee de la variable de entorno `GUEST_PASSWORD`; si no
  existe, cae a `invitado` emitiendo un warning en `stderr`.
- **Artefacto:** `scripts/seed_invitado.py`, reutiliza `GestionarUsuariosUseCase`
  y `MySQLUsuariosRepository` (mismo patrón que `scripts/seed_admin.py`).
- **Sin cambios en `src/`:** `UserModel.role`, `MySQLUsuariosRepository`,
  `GestionarUsuariosUseCase.crear_usuario(rol=...)` y el claim `rol` del JWT ya
  soportan la feature.

## 2. Dominio y Puertos

Sin cambios en `domain/auth/`. Reutiliza:

- `UsuarioAuth` (`src/domain/auth/entities.py`).
- `RepositorioUsuariosPort`, `GeneradorTokenPort` (`src/domain/auth/ports.py`).
- `HashContrasenaService` (`src/domain/auth/services.py`).

## 3. Casos de Uso

- `GestionarUsuariosUseCase.crear_usuario("invitado", contrasena,
  esta_activo=True, rol="invitado")` — idempotente: si el usuario ya existe, lo
  devuelve sin sobrescribir.

## 4. Script de seed (`scripts/seed_invitado.py`)

- Constante `USUARIO_INVITADO = "invitado"`, `CONTRASENA_DEFAULT = "invitado"`.
- `obtener_contrasena(environ: dict[str, str] | None = None) -> str`:
  - `GUEST_PASSWORD` presente → la devuelve sin warning.
  - ausente → emite warning a `stderr` y devuelve `invitado`.
- `crear_invitado(repo_usuarios, hash_service, contrasena) -> UsuarioAuth`:
  orquesta `GestionarUsuariosUseCase` con `rol="invitado"`.
- `main()`: obtiene contraseña, abre sesión vía `get_session_factory()`, crea el
  usuario, imprime resumen, `sys.exit(1)` ante error y cierra la sesión en
  `finally`.

## 5. Matriz de Pruebas (RED Suite)

### `tests/unit/test_seed_invitado.py`

1. `test_obtener_contrasena_respeta_env` — `GUEST_PASSWORD` se respeta sin warning.
2. `test_obtener_contrasena_default_invitado_con_warning` — sin env devuelve
   `invitado` y emite warning en `stderr`.
3. `test_crear_invitado_rol_y_hash` — entidad con `rol="invitado"`, hash scrypt
   que no contiene la contraseña.
4. `test_crear_invitado_idempotente` — dos llamadas → un solo usuario, mismo `id`.
5. `test_login_invitado_token_rol_invitado` — login de `invitado`/`invitado`
   genera token cuyo claim `rol` es `invitado`.

## 6. Criterios del Gauntlet

```bash
bash scripts/ci.sh
```

`__init__.py` de 0 bytes. `domain/auth/` sin terceros. Cobertura del módulo de
seed y del flujo de login invitado cubierta por la suite unitaria.
