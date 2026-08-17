# Spec F: Endurecimiento de Ciberdefensa (Postura Segura por Defecto)

## 1. Objetivo y Contexto

Endurecer `datamaq-telemetry` contra los vectores de ataque detectados en la
auditoría (V1–V12). Objetivo: **seguridad por defecto** — una instancia sin
`.env` personalizado no debe quedar expuesta. Alcance acotado a configuración,
autenticación, ingesta MQTT, sanitización de entrada y gestión de secretos.
**Fuera de alcance:** cambios de esquema de BD, pasarela de pago, registro
público de usuarios.

**Decisiones aprobadas (usuario):**

- **Autenticación obligatoria por defecto** en toda la API (flag
  `AUTH_REQUIRED` desactivable solo para desarrollo local).
- **Un único `spec.md`** (este documento) con las 6 fases y su matriz BDD.

**Inventario de vulnerabilidades (origen del alcance):**

| # | Severidad | Hallazgo |
|---|-----------|----------|
| V1 | CRÍTICA | API sin autenticación (`get_usuario_actual` sin aplicar); `purge` y WS públicos |
| V2 | CRÍTICA | `API_SECRET_KEY` con default hardcodeado |
| V3 | CRÍTICA | Defaults de BD `root`/vacío |
| V4 | CRÍTICA | MQTT sin TLS + `allow_anonymous true` |
| V5 | ALTA | Auto-registro de dispositivos por MAC |
| V6 | ALTA | Login sin rate limit + DTO sin `max_length` (DoS scrypt) |
| V7 | ALTA | `DEBUG=True`, `CORS_ORIGINS="*"`, `API_HOST="0.0.0.0"` por defecto |
| V8 | ALTA | `payload_bruto` y mensajes de alerta sin sanear |
| V9 | MEDIA | `float(v)` sin validación previa en parser MQTT |
| V10 | MEDIA | Logs con payload completo en claro |
| V11 | MEDIA | JWT 8 h, sin `iat`/`rol` |
| V12 | MEDIA | `seed_admin.py` con contraseña por CLI |

---

## 2. Dominio y Puertos

Sin dependencias de terceros en `domain/` (solo stdlib).

### `src/domain/auth/entities.py`

- `UsuarioAuth` agrega `rol: str = "operador"`.

### `src/domain/auth/exceptions.py`

- `DemasiadosIntentosError(DominioAuthException)` — bloqueo por fuerza bruta.

### `src/domain/auth/services.py`

- `RateLimiterService` (ventana fija en memoria, puro):
  - `__init__(max_intentos: int, ventana_segundos: int)`
  - `permitir(clave: str, ahora: datetime | None = None) -> bool`
  - `registrar_intento(clave: str, ahora: datetime | None = None) -> None`
  - `resetear(clave: str) -> None`

### `src/domain/auth/ports.py`

- `GeneradorTokenPort.generar(self, usuario_id, usuario, expira_en,
  rol: str = "operador") -> str`.

---

## 3. Casos de Uso y DTOs

### `src/application/dtos/auth_dto.py`

- `LoginRequestDTO`: `usuario`/`contrasena` con `Field(min_length=1,
  max_length=128)`.

### `src/application/use_cases/autenticar_usuario.py`

- `AutenticarUsuarioUseCase(..., rate_limiter=None, max_intentos=5,
  ventana_segundos=300)`:
  - Antes de verificar credenciales, si `rate_limiter` no `permitir(nombre)` →
    `DemasiadosIntentosError`.
  - Credenciales inválidas → `registrar_intento(nombre)`.
  - Login exitoso → `resetear(nombre)`.
  - Token incluye `rol=usuario.rol`.

### `src/application/use_cases/ingestar_telemetria.py`

- `IngestarTelemetriaUseCase(..., permitir_auto_registro: bool = True)`.
- `_obtener_o_crear_dispositivo` devuelve `Dispositivo | None`; si el dispositivo
  no existe y `not permitir_auto_registro` → `None` (se descarta el mensaje).
- Subtópico `status`: validar `direccion_ip` con `ipaddress`; conversión segura a
  `int` de `wifi_rssi_dbm`/`wifi_calidad`/`tiempo_activo_segundos`; `payload_bruto`
  acotado a `{"wifi_sta", "device_info"}`.

---

## 4. Infraestructura

### `src/infrastructure/settings/config.py`

Cambios de defaults: `DEBUG=False`, `API_HOST="127.0.0.1"`,
`CORS_ORIGINS=""`, `API_SECRET_KEY=""`, `AUTH_TOKEN_EXPIRA_MINUTOS=120`.

Nuevos campos: `AUTH_REQUIRED=True`, `API_EXPOSE_DOCS=True`,
`MQTT_TLS_ENABLED=False`, `MQTT_TLS_CA_CERTS=""`, `MQTT_MAX_PAYLOAD_BYTES=65536`,
`MQTT_AUTO_REGISTER_DEVICES=True`, `LOGIN_MAX_INTENTOS=5`,
`LOGIN_VENTANA_SEGUNDOS=300`.

`model_validator(mode="after")` `validar_configuracion`:
- Si `not DEBUG`: exige `API_SECRET_KEY` no vacío y no débil
  (`dev-secret-key-datamaq`, `change-this-secret-key-in-production`), y
  `DB_PASSWORD` no vacío → `ValueError`.
- Si `DEBUG` y `API_SECRET_KEY==""`: autogenera con `secrets.token_urlsafe(32)`.

### `src/infrastructure/auth/jwt_token_service.py`

- `generar(..., rol="operador")` → payload `{sub, usuario, exp, rol, iat}`.
- `verificar` mantiene firma HMAC-SHA256 y expiración; devuelve claims con `rol`.

### `src/infrastructure/fastapi/dependencies.py`

- `get_usuario_actual`: si `not AUTH_REQUIRED` → claims `{"sub":"anon",
  "rol":"admin", "usuario":"anon"}`; si no, valida Bearer (401).
- `requiere_rol_admin`: dependencia que exige `claims["rol"] == "admin"` (403).
- `get_auth_controller`: inyecta `RateLimiterService` singleton.

### `src/infrastructure/fastapi/server.py`

- `include_router(..., dependencies=[Depends(get_usuario_actual)])` para
  `telemetria`, `dispositivos`, `organizaciones`, `planes`, `alertas`.
- `auth_router` (login) y `/health` públicos.
- `docs_url`/`openapi_url` condicionales a `API_EXPOSE_DOCS`.
- WS `/ws/live`: valida token si `AUTH_REQUIRED` (factorizado `_token_valido`).

### `src/infrastructure/fastapi/routes/system_router.py`

- `POST /api/system/purge` con `Depends(requiere_rol_admin)`.

### `src/infrastructure/paho_mqtt/mqtt_listener.py`

- `tls_set(ca_certs=...)` si `MQTT_TLS_ENABLED`.
- Descartar payload > `MQTT_MAX_PAYLOAD_BYTES`.
- Pasar `permitir_auto_registro` al use case.
- Eliminar payload completo del log debug.

### `src/infrastructure/settings/logger.py`

- Processor `redactar_secretos` que enmascara claves `password`, `contrasena`,
  `token`, `secret`, `authorization`, `api_key`.

### `src/adapters/presenters/error_presenter.py`

- `DemasiadosIntentosError` → `429`.

### `src/infrastructure/sqlalchemy/models.py` y `mysql_repositories.py`

- `UserModel.role` (String 20, default `"operador"`); mapeo `rol` en
  `MySQLUsuariosRepository`.

### `scripts/seed_admin.py`

- Eliminar flag `--contrasena`; leer `ADMIN_PASSWORD` (env) o `getpass`.

---

## 5. Matriz de Pruebas (RED Suite)

### `tests/unit/test_security_config.py` (Fase 1)

1. `test_debug_default_false` — `Settings().DEBUG is False`.
2. `test_api_host_default_loopback` — `Settings().API_HOST == "127.0.0.1"`.
3. `test_cors_default_vacio` — `Settings().CORS_ORIGINS == ""`.
4. `test_secret_key_default_vacia` — `Settings().API_SECRET_KEY == ""`.
5. `test_token_expiracion_corta_default` — `AUTH_TOKEN_EXPIRA_MINUTOS <= 120`.
6. `test_auth_required_default_true` — `AUTH_REQUIRED is True`.
7. `test_produccion_rechaza_secreto_debil` — con `DEBUG=False` y secreto débil
   lanza `ValidationError`.
8. `test_produccion_rechaza_db_password_vacia` — con `DEBUG=False` y
   `DB_PASSWORD=""` lanza `ValidationError`.
9. `test_dev_autogenera_secreto_vacio` — con `DEBUG=True` y `API_SECRET_KEY=""`
   autogenera un secreto no vacío.

### `tests/unit/test_security_auth.py` (Fase 2)

1. `test_rate_limiter_permite_dentro_de_ventana`
2. `test_rate_limiter_bloquea_tras_exceder`
3. `test_rate_limiter_reset_tras_login_exitoso`
4. `test_login_bloqueado_tras_exceder_intentos` — `DemasiadosIntentosError`.
5. `test_jwt_incluye_rol_e_iat` — claims con `rol` y `iat`.
6. `test_requiere_rol_admin_rechaza_operador` — 403.
7. `test_get_usuario_actual_anonimo_sin_auth_required` — con `AUTH_REQUIRED=False`
   devuelve claims anónimos con `rol=admin`.
8. `test_error_presenter_mapea_429` — `DemasiadosIntentosError` → 429.

### `tests/unit/test_security_mqtt.py` (Fase 3)

1. `test_listener_descarta_payload_grande` — payload > límite no procesado.
2. `test_sin_auto_registro_descarta_mac_desconocida` — no crea dispositivo.
3. `test_tls_configurado_cuando_habilitado` — `tls_set` invocado.
4. `test_log_debug_sin_payload` — el log no incluye el payload bruto.

### `tests/unit/test_security_sanitizacion.py` (Fase 4)

1. `test_login_dto_rechaza_usuario_largo` — 129 chars → `ValidationError`.
2. `test_login_dto_rechaza_contrasena_larga` — 129 chars → `ValidationError`.
3. `test_ip_invalida_descartada` — `direccion_ip` inválida → `None`.
4. `test_rssi_no_numerico_descartado` — `wifi_rssi_dbm` no numérico → `None`.
5. `test_payload_bruto_acotado` — log guarda solo claves permitidas.

### `tests/unit/test_security_ops.py` (Fase 5)

1. `test_seed_admin_rechaza_flag_contrasena` — `--contrasena` no aceptado.
2. `test_seed_admin_lee_contrasena_de_env` — usa `ADMIN_PASSWORD`.

### `tests/unit/test_security_docs.py` (Fase 6)

1. `test_readme_tiene_threat_model` — `README.md` contiene sección de seguridad.

### `tests/integration/test_security_api.py`

1. `test_create_app_requiere_auth_en_telemetria` — rutas de telemetría tienen
   dependencia de autenticación.
2. `test_purge_requiere_admin` — `/api/system/purge` exige rol admin.

---

## 6. Criterios del Gauntlet

```bash
venv/bin/python scripts/verify_architecture.py
venv/bin/ruff check .
venv/bin/ruff format --check .
venv/bin/pytest --cov=src
venv/bin/pyright src/
```

Reglas inmutables: `__init__.py` de 0 bytes; prohibidos `# type: ignore`,
`# noqa`, `cast(Any, ...)`, `@pytest.mark.skip`; cero re-exportaciones.
Cobertura global de `src/` no se fija con `--cov-fail-under` global (código
preexistente MQTT/MySQL fuera de alcance); los módulos nuevos y modificados
deben quedar con cobertura relevante.
