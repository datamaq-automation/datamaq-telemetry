# Spec: invitado@ ve el listado global de usuarios en api-dev (solo lectura)

**Issue:** datamaq-automation/datamaq#102
**Decisión:** `decisions/2026-10-30_invitado-listado-usuarios-develop.md`
**Relacionada:** `decisions/2026-10-29_invitado-develop-replica.md`, `specs/develop-replica-y-flujo-en-vivo.md`
**Rama:** `feat/invitado-listado-usuarios-dev`

## 1. Objetivo y Contexto

La cuenta `invitado@datamaq.com.ar` (rol `operador`, en api-dev) debe poder listar todos los usuarios de
api-dev: email, rol y organización. Solo lectura. Sin alta, baja ni cambio de rol. No aplica a producción.

Verificado contra código (2026-10-30):

- `src/infrastructure/fastapi/routes/usuarios_router.py` no tiene ruta de listado. Todas sus rutas exigen
  `requiere_rol_admin` (`src/infrastructure/fastapi/dependencies.py:485`: solo `admin` y `superadmin`).
- `ROLES_ACCESO_GLOBAL` = `{superadmin}` (`src/domain/auth/services.py:71`), ampliable con
  `ROLES_ACCESO_GLOBAL_EXTRA` solo en api-dev (`src/infrastructure/settings/config.py:49,163`).
- `compat_roles_invitado.py` cubre solo los roles retirados `invitado` e `invitado_global`. No toca `operador`.
- En api-dev, `SoloLecturaMiddleware` (`API_SOLO_LECTURA=true`, `solo_lectura_middleware.py`) rechaza todo método
  no-GET. El listado queda como solo lectura por construcción en api-dev, sin depender del rol.
- El rol `solo_lectura` (decisión 2026-10-29 D3) existe, pero la decisión de 2026-10-30 pide `operador`.
  La restricción de solo lectura la da el guard de api-dev, no el rol.

## 2. Dominio & Puertos

Sin cambios en entidades ni en `RepositorioUsuariosPort`, que ya expone lo necesario para listar.

- **Verificar antes de implementar:** si `RepositorioUsuariosPort` no tiene `listar_todos()` (o equivalente
  paginado), agregarlo al puerto y al repositorio SQLAlchemy (`usuarios_repository.py`). Es lectura pura.
- **Política de visibilidad (función pura en `src/domain/auth/services.py`):**
  `puede_listar_usuarios(rol: str, extra: str, es_produccion: bool) -> bool`
  - `superadmin`, `admin`: sí (sin cambios).
  - `operador`: sí solo si `LISTADO_USUARIOS_OPERADOR` está activo. Ese flag es `False` por defecto y **no puede
    activarse en producción** (validación en `config.py`, mismo patrón que `ROLES_ACCESO_GLOBAL_EXTRA`).
  - Otros roles: no.
- **Filtro de visibilidad (función pura):** `filtrar_usuarios_visibles(usuarios, rol_solicitante)`.
  - **Implementación literal de la decisión ("todos los usuarios"):** devuelve todas las filas, sin filtrar por rol.
  - **Supuesto abierto (no resuelto):** si el dueño decide excluir superadmin para `operador`, el cambio es
    una sola condición en esta función (excluir `rol == "superadmin"` cuando el solicitante no es `superadmin`).
    Ver sección 6. No se implementa hasta que el dueño lo confirme.

## 3. Casos de Uso & DTOs

### Caso de uso: `ListarUsuariosUseCase` (`src/application/use_cases/listar_usuarios.py`)

- Entrada: `rol_solicitante: str`.
- Llama a `repo.listar_todos()`, aplica `filtrar_usuarios_visibles`, devuelve `list[UsuarioListadoDTO]`.
- No modifica nada: no llama a `guardar`, `eliminar` ni auditoría de escritura.

### DTO: `UsuarioListadoDTO` (`src/application/dtos/usuario_listado_dto.py`, Pydantic v2)

| Campo | Tipo | Nota |
|---|---|---|
| `id` | `str` | |
| `usuario` | `str` | email de la cuenta |
| `rol` | `str` | |
| `organizacion_id` | `str \| None` | |
| `esta_activo` | `bool` | |

No incluye hash de contraseña, `totp_secret` ni fechas internas.

### Ruta: `GET /api/v1/usuarios` (`usuarios_router.py`)

- Dependencia: `requiere_listado_usuarios` (nueva, en `dependencies.py`), que deja pasar a `admin`/`superadmin`
  y a `operador` solo si `puede_listar_usuarios` lo permite.
- Responde `list[UsuarioListadoDTO]`.
- Las rutas existentes de alta, baja, cambio de rol y plantas siguen con `requiere_rol_admin` sin cambios.
  El `operador` no gana permisos de escritura.

### Configuración

- `LISTADO_USUARIOS_OPERADOR: bool = False` en `config.py`. Se activa solo en api-dev.
- Validación: si `es_produccion` y el flag está activo, `ValueError` (igual que `ROLES_ACCESO_GLOBAL_EXTRA`).

### Frontend (punto 4 del traspaso)

- La pantalla de usuarios de `app-datamaq` **no** se muestra al invitado en esta spec. Requiere decisión
  explícita del dueño. Esta spec solo habilita el endpoint.

## 4. Matriz de Pruebas

Todas con mocks/fixtures, sin MySQL real (`tests/unit/`).

| Caso | Tipo | Resultado esperado |
|---|---|---|
| `puede_listar_usuarios` con `superadmin`/`admin` | unit | `True` |
| `puede_listar_usuarios` con `operador`, flag `False` | unit | `False` |
| `puede_listar_usuarios` con `operador`, flag `True`, no producción | unit | `True` |
| Validación de config: flag `True` + producción | unit | `ValueError` |
| `filtrar_usuarios_visibles` como `operador` | unit | devuelve todas las filas, incluido superadmin (literal) |
| `ListarUsuariosUseCase` no llama a `guardar` | unit | `guardar` nunca invocado |
| `GET /api/v1/usuarios` con `operador` y flag `False` | router | 403 `forbidden` |
| `GET /api/v1/usuarios` con `operador` y flag `True` | router | 200, lista todas las filas (incluye superadmin, supuesto abierto) |
| `GET /api/v1/usuarios` sin token | router | 401 |
| `POST /api/v1/usuarios` con `operador` | router | 403 (sigue sin alta) |
| `DELETE`/`PATCH` con `operador` | router | 403 |
| Respuesta no contiene hash ni `totp_secret` | router | claves ausentes |
| `GET` en api-dev con `API_SOLO_LECTURA=true` | integración de middleware | 200 |
| `POST /api/v1/usuarios` en api-dev con `API_SOLO_LECTURA=true` | integración de middleware | 403 |

## 5. Criterios del Gauntlet

- `APP_ENV=test ./scripts/pre-push.sh` verde en la rama (etapas 1–4).
- `ruff check .` sin errores (no solo `ruff format`).
- `verify_architecture.py` y `verify_code_size.py` verdes. Nota: `server.py` está en 541/550 líneas. No agregar
  código ahí; el router nuevo va en `usuarios_router.py`.
- Cobertura unitaria >= 85% sin bajar la actual.
- Commits atómicos por capa (`feat(dominio)`, `feat(aplicacion)`, `feat(api)`, `test(...)`), cada uno con
  `Refs #102` (`Closes #102` solo en el PR a `develop`).
- Push solo a `feat/invitado-listado-usuarios-dev`. Nunca a `main`. Sin `--force`.

## 6. Dudas y decisiones pendientes (para el padre)

1. **Superadmin en el listado del invitado (abierto):** la decisión dice "todos"; #40 limita a admin. Esta spec
   implementa "todos". Si el dueño decide excluir superadmin, es un cambio de una condición en
   `filtrar_usuarios_visibles`. Lo decide el dueño, no la sesión.
2. **Rama base:** el traspaso dice `dev`, pero el repo tiene `develop`. Se usó `develop`.
3. **Cuenta `invitado@` en api-dev (paso 2 del traspaso):** es escritura en la base de api-dev con credenciales.
   No se ejecuta desde esta sesión sin autorización del dueño en esta sesión. No es bloqueador de código.
4. **Frontend:** mostrar la pantalla al invitado requiere decisión del dueño (fuera de alcance).
