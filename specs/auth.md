# Spec E: Autenticación JWT (`POST /api/auth/login`)

## 1. Objetivo y Contexto

Habilitar la autenticación real de `datamaq-telemetry` según el contrato
`app-datamaq/docs/contrato-auth.md`, para que la SPA deje de usar el login demo
local de su Fase 1.

**Decisiones aprobadas:**

- **Mecanismo de token:** JWT stateless firmado con `HMAC-SHA256` (HS256)
  usando `API_SECRET_KEY` (ya existente en `Settings`). Sin dependencias nuevas:
  `hmac`/`hashlib`/`base64`/`json` son stdlib y la firma vive en infraestructura.
- **Hash de contraseña:** `hashlib.scrypt` (stdlib), salt aleatorio de 16 bytes,
  formato de almacenamiento `scrypt$n$r$p$salt_b64$digest_b64`.
- **Alcance de guardas:** se implementa `POST /api/auth/login` más el servicio y
  la dependencia de verificación (`get_usuario_actual`), **pero sin activar
  guardas** en las rutas existentes (opción A). La protección se activa en una
  iteración coordinada con la migración de `app-datamaq`.
- **Bootstrap de usuarios:** script `scripts/seed_admin.py` (idempotente, hash
  scrypt). Sin endpoint de registro público.
- **Expiraciones:** `AUTH_TOKEN_EXPIRA_MINUTOS: int = 480` (8 h) en `Settings`.

**Alcance de esta iteración:** dominio `auth`, repositorio de usuarios, hash y
política de expiración, generación/verificación JWT, caso de uso de login, DTOs,
router `POST /api/auth/login`, dependencia de verificación inactiva y
seed admin. Nota KISS: no se crea `usuario_mapper.py` porque no existe
transformación entidad→DTO en este alcance (login devuelve `token` + `expira_en`,
no la entidad).

## 2. Dominio y Puertos

Sin dependencias externas en `domain/auth/` (solo stdlib):

### `src/domain/auth/exceptions.py`

- `DominioAuthException(Exception)` — base con atributo `mensaje`.
- `NombreUsuarioInvalidoError` — nombre de usuario vacío.
- `CredencialesInvalidasError` — usuario inexistente o contraseña incorrecta.
- `UsuarioInactivoError` — cuenta deshabilitada.

### `src/domain/auth/entities.py`

- `UsuarioAuth` (dataclass):
  - `id: str`
  - `usuario: str`
  - `hash_contrasena: str`
  - `esta_activo: bool = True`
  - `creado_en: datetime = field(default_factory=ahora_utc)`
  - `actualizado_en: datetime = field(default_factory=ahora_utc)`

### `src/domain/auth/value_objects.py`

- `NombreUsuario` (`@dataclass(frozen=True)`): `valor: str`, normaliza a
  minúsculas y recorta espacios; lanza `NombreUsuarioInvalidoError` si queda
  vacío.

### `src/domain/auth/ports.py`

- `RepositorioUsuariosPort(ABC)`:
  - `obtener_por_usuario(usuario: str) -> UsuarioAuth | None`
  - `guardar(usuario: UsuarioAuth) -> UsuarioAuth`
- `GeneradorTokenPort(ABC)`:
  - `generar(usuario_id: str, usuario: str, expira_en: datetime) -> str`
  - `verificar(token: str) -> dict[str, Any] | None`

### `src/domain/auth/services.py`

- `HashContrasenaService`:
  - `generar_hash(contrasena: str) -> str` — scrypt, salt aleatorio.
  - `verificar(contrasena: str, hash_almacenado: str) -> bool` — compara con
    `hmac.compare_digest`; `False` ante formato inválido.
- `PoliticaExpiracionService`:
  - `calcular_expiracion(ahora: datetime, minutos_validez: int) -> datetime`.

## 3. Casos de Uso y DTOs

### `src/application/dtos/auth_dto.py`

- `LoginRequestDTO(BaseModel)`: `usuario: str`, `contrasena: str`.
- `LoginResponseDTO(BaseModel)`: `token: str`, `expira_en: datetime`.

### `src/application/use_cases/autenticar_usuario.py`

- `AutenticarUsuarioUseCase(repo_usuarios, hash_service, token_service,
  minutos_validez)`:
  - `login(dto: LoginRequestDTO) -> LoginResponseDTO`
  - Normaliza usuario con `NombreUsuario`.
  - Usuario inexistente o hash inválido → `CredencialesInvalidasError`.
  - `esta_activo=False` → `UsuarioInactivoError`.
  - Genera `expira_en` con `PoliticaExpiracionService` y firma el token.

### `src/application/use_cases/gestionar_usuarios.py`

- `GestionarUsuariosUseCase(repo_usuarios, hash_service)`:
  - `crear_usuario(usuario, contrasena, esta_activo=True) -> UsuarioAuth`
  - Idempotente: si el usuario ya existe, lo devuelve sin sobrescribir.

## 4. Adaptadores e Infraestructura

- `src/infrastructure/auth/jwt_token_service.py` — `JwtTokenService(secreto)`
  que implementa `GeneradorTokenPort`: header `{"alg":"HS256","typ":"JWT"}`,
  payload `{"sub","usuario","exp"}`, base64url sin padding, firma
  `HMAC-SHA256`. `verificar` devuelve `None` si la firma no coincide, el payload
  no es JSON válido o `exp` ya venció.
- `src/infrastructure/sqlalchemy/models.py` — `UserModel` (tabla `users`):
  `id` (String 36, PK), `username` (String 150, unique, index),
  `password_hash` (String 255), `is_active` (bool), `created_at`, `updated_at`.
- `src/infrastructure/sqlalchemy/mysql_repositories.py` —
  `MySQLUsuariosRepository(RepositorioUsuariosPort)`.
- `src/infrastructure/fastapi/routes/auth_router.py` — `APIRouter(prefix="/api/auth")`:
  - `POST /login` → `login`.
- `src/infrastructure/fastapi/dependencies.py`:
  - `get_auth_use_case` (ensambla repo + hash + JWT + use case).
  - `get_usuario_actual` (dependencia Bearer que verifica el JWT; **no aplicada
    a rutas existentes**).
- `src/infrastructure/fastapi/server.py` — registrar `auth_router`.
- `src/infrastructure/settings/config.py` — `AUTH_TOKEN_EXPIRA_MINUTOS: int = 480`.
- `src/adapters/presenters/error_presenter.py` — mapeo:
  - `CredencialesInvalidasError` → `401`, `detail="credenciales_invalidas"`.
  - `UsuarioInactivoError` → `403`, `detail="usuario_inactivo"`.
- `scripts/seed_admin.py` — CLI `--usuario --contrasena`, idempotente.

## 5. Matriz de Pruebas (RED Suite)

### `tests/unit/test_auth.py`

1. `test_nombre_usuario_normaliza` — recorta y pasa a minúsculas.
2. `test_hash_scrypt_genera_y_verifica` — hash válido verifica True.
3. `test_hash_scrypt_salt_aleatorio` — dos hashes de la misma pass difieren.
4. `test_hash_scrypt_no_revela_contrasena` — el hash no contiene la pass.
5. `test_hash_scrypt_verificar_incorrecta_o_malformado` — False.
6. `test_login_exitoso` — token no vacío, `expira_en` futuro.
7. `test_login_usuario_inexistente` — `CredencialesInvalidasError`.
8. `test_login_contrasena_incorrecta` — `CredencialesInvalidasError`.
9. `test_login_usuario_inactivo` — `UsuarioInactivoError`.
10. `test_jwt_generar_y_verificar` — claims `sub`/`usuario`/`exp`.
11. `test_jwt_token_manipulado` — `verificar` → `None`.
12. `test_jwt_token_expirado` — `verificar` → `None`.
13. `test_politica_expiracion` — suma `minutos_validez`.
14. `test_crear_usuario_idempotente` — no duplica ni sobrescribe.
15. `test_repositorio_usuarios_sqlite` — `guardar` + `obtener_por_usuario`
    (SQLite in-memory sobre `UserModel`).
16. `test_login_handler_exitoso` — handler `auth_router.login` devuelve
    `LoginResponseDTO` con token.
17. `test_login_handler_credenciales_invalidas` — handler lanza
    `HTTPException(401, "credenciales_invalidas")`.
18. `test_login_handler_usuario_inactivo` — handler lanza
    `HTTPException(403, "usuario_inactivo")`.
19. `test_get_usuario_actual_valido` — Bearer válido devuelve claims.
20. `test_get_usuario_actual_sin_header` — sin header lanza `HTTPException(401)`.
21. `test_get_usuario_actual_token_invalido` — token falso lanza
    `HTTPException(401)`.

### `tests/integration/test_auth_api.py`

1. `test_create_app_registra_router_auth` — `create_app()` expone
   `POST /api/auth/login`.

## 6. Criterios del Gauntlet

```bash
.venv/bin/python scripts/verify_architecture.py
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest --cov=src
.venv/bin/pyright src/
```

Criterio de cobertura de esta iteración: el módulo `auth` (dominio, aplicación,
adaptadores e infraestructura) queda por encima del 90 %. La cobertura global de
`src/` incluye código preexistente (MQTT, repositorios MySQL, routers, `server`,
`main`, `logger`) fuera del alcance de autenticación, por lo que no se aplica
`--cov-fail-under` global en esta Spec.

`__init__.py` de 0 bytes (sin re-exportaciones). `domain/auth/` sin terceros.
