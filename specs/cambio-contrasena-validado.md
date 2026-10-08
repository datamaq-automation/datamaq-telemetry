# Cambio de contraseña autenticado con código OTP por email

Bloque backend de la spec del padre `specs/cambio-contrasena-validado.md` y decisión
`decisions/2026-10-05_cambio-contrasena-con-validacion-email.md`. Decisiones A–E confirmadas por el
padre el 2026-10-08. Los endpoints stub de producción quedaron deshabilitados por el hotfix `c826a80`.

## 1. Objetivo y Contexto

Un usuario autenticado cambia su contraseña confirmando un código de 4 dígitos enviado a su email.
Corrige los stubs desplegados (`PATCH /request-password-change-code` y `/confirm-password-change`
devolvían 200 y auditaban un cambio que no ocurría).

**Correcciones respecto de la spec del padre:**
- La ruta del router es `src/infrastructure/fastapi/routes/auth_router.py` (no `fastapi/auth_router.py`).
- Los tests citados en la spec original (`tests/unit/test_cambio_contrasena.py`,
  `tests/integration/test_auth_endpoints.py::cambio_contrasena`) no existían. Los reales están en la sección 4.
- El placeholder de integración `tests/integration/test_cambio_contrasena_endpoints.py` se eliminó.
- La auditoría va a la tabla `auditoria_cambio_contrasena` (no al sistema de auditoría general).

## 2. Dominio y puertos

- `src/domain/usuarios/servicios_contrasena.py`: `GeneradorCodigoOTP` (CSPRNG `secrets`, HMAC-SHA256
  con `hmac.compare_digest`), `ValidadorContraseña` (≥8, mayúscula, minúscula, dígito),
  `ServicioTTLValidacion` (TTL 10 min, 5 intentos por código, 5 solicitudes por 10 min).
- `src/domain/auth/entities.py`: `ValidacionCambioContrasena`.
- `src/domain/auth/exceptions.py`: `CodigoCambioInvalidoError` (400), `NoSePudoEnviarCodigoError` (503).
- `src/domain/auth/ports.py`: `RepositorioCambioContrasenaPort`; `ServicioEmailPort` suma
  `enviar_codigo_cambio_contrasena` y `notificar_cambio_contrasena`.

## 3. Casos de uso y DTOs

- `src/application/use_cases/cambio_contrasena.py`:
  - `SolicitarCambioContrasenaUseCase`: valida `password_actual` (401, audita `intento_fallido`), aplica
    el límite (429) contando filas de `cambio_contrasena_validaciones` en 10 min, invalida el código
    anterior, guarda el HMAC y envía el email. Si el envío falla, responde 503 y no reporta éxito.
  - `ConfirmarCambioContrasenaUseCase`: valida el código (400 si es inexistente, expirado, usado o
    bloqueado). Cada fallo incrementa `intentos_fallidos`; al quinto invalida el código y audita
    `bloqueo_por_intentos`. Después valida la política y `nueva != actual` (400) sin consumir el código,
    cambia el hash, fija `sesiones_revocadas_antes_de` (invalida sesiones en BD) y notifica por email
    sin revertir el cambio si el envío falla.
- DTOs (`src/application/dtos/cambio_contrasena_dto.py`): `codigo` con patrón `^[0-9]{4}$` (422);
  `password_nueva == password_nueva_confirm` (422).
- Errores HTTP: 401 credenciales, 400 `codigo_invalido_o_expirado` o `contrasena_debil`, 422 validación, 429, 503 `envio_codigo_no_disponible`.

## 4. Matriz de pruebas

| Caso | Test |
|------|------|
| Código 4 dígitos, HMAC guardado, TTL 10 min, email ofuscado | `tests/unit/test_cambio_contrasena_casos_uso.py::test_solicitar_envia_codigo_y_guarda_solo_el_hmac` |
| 401 password actual incorrecta (sin enviar ni crear) | `test_password_actual_incorrecta_da_401_sin_enviar_ni_crear` y `tests/unit/test_cambio_contrasena_endpoints.py::test_solicitar_con_password_incorrecta_responde_401_y_no_envia` |
| 429 sexta solicitud en 10 min | `test_sexta_solicitud_en_diez_minutos_responde_429` |
| Nueva solicitud invalida la anterior | `test_nueva_solicitud_invalida_la_anterior` |
| 400 código erróneo / sin vigente / expirado / reutilizado | `test_codigo_erroneo_cuenta_intento_y_da_400`, `test_codigo_expirado_da_400`, `test_codigo_no_se_reutiliza_tras_el_cambio`, `test_confirmar_sin_codigo_vigente_responde_400` |
| Bloqueo al quinto intento | `test_quinto_intento_fallido_invalida_el_codigo_y_audita_bloqueo` |
| 400 política débil y nueva == actual, sin consumir código | `test_contrasena_nueva_debil_da_400_y_no_consume_codigo`, `test_contrasena_nueva_igual_a_la_actual_da_400` |
| 422 formato de código y confirmación distinta | `test_confirmar_con_codigo_mal_formado_responde_422`, `test_confirmar_con_contrasenas_distintas_responde_422` |
| 200 cambio: hash nuevo, sesiones revocadas, auditoría | `test_confirmar_cambia_hash_consume_codigo_revoca_sesiones_y_audita`, `test_confirmar_con_codigo_correcto_responde_200_y_cambia_contrasena` |
| Email caído: solicitud 503, confirmación no revierte | `test_fallo_de_email_de_confirmacion_no_revierte_el_cambio`, `test_fallo_de_email_no_se_reporta_como_exito` |
| Sin token → 401 | `test_solicitar_sin_autenticacion_responde_401` |
| Persistencia: solo HMAC, límites por ventana, consumo por usuario | `tests/unit/test_repositorio_cambio_contrasena.py` |
| Emails sin código en logs ni contraseña en cuerpo | `tests/unit/test_email_cambio_contrasena.py` |
| Settings: `OTP_HMAC_KEY` obligatoria y distinta en producción | `tests/unit/test_otp_hmac_key_config.py` |

## 5. Criterios del gauntlet

- `scripts/pre-push.sh` en verde antes de cada commit relevante.
- `scripts/verify_architecture.py` y `scripts/verify_code_size.py` en verde.
- Migración `b7c3d9e1f2a4` encadenada desde `1a35ebb54900`; `REVISION_HEAD` y `docs/database_erd.md` actualizados.

## Despliegue

**Paso obligatorio para activar el cambio de contraseña:** cargar `OTP_HMAC_KEY` en el `.env` del VPS
(`/var/www/datamaq-telemetry`), con al menos 16 caracteres y distinta de `API_SECRET_KEY`. Generar con
`python -c "import secrets; print(secrets.token_urlsafe(32))"`.

- Sin la clave, la API **arranca igual** (no tumba el resto de los endpoints): loguea un error crítico
  y los dos endpoints de cambio de contraseña responden **503** sin enviar código ni tocar la BD.
- La migración `b7c3d9e1f2a4` corre en el deploy (ver punto 2 de Pendientes).

## Pendientes y riesgos (deciden el padre o el dueño)

1. **Despliegue:** resuelto en el código (ver sección Despliegue). Falta cargar la clave en el VPS antes de que el cambio de contraseña funcione.
2. **Migración en producción:** `b7c3d9e1f2a4` hace DROP de `codigo` en `cambio_contrasena_validaciones`. La tabla debe estar vacía: verificado en el código (ninguna ruta escribió nunca en ella), sin consulta a producción. El deploy ejecuta migraciones; requiere autorización del dueño.
3. **Adivinación de `password_actual`:** resuelto. El límite de 5 por 10 min cuenta solicitudes emitidas más eventos `intento_fallido` de la auditoría del usuario, y el chequeo ocurre antes de verificar la contraseña. Un éxito no resetea el límite dentro de la ventana. Efecto colateral: los códigos erróneos también consumen presupuesto (más restrictivo).
4. **IP de auditoría (deuda):** reutiliza `_obtener_ip_cliente`, que confía en `X-Forwarded-For` (falsificable). Es el patrón existente de la app; no se cambió.
5. **Atomicidad (deuda, no implementada):** "consumir código + guardar hash + revocar sesiones" no ocurre en una sola transacción. Motivo: cada repositorio hace `commit()` por su cuenta (`MySQLUsuariosRepository.guardar` lo usan más de seis llamadores) y no hay unidad de trabajo. Hacerlo transaccional exige introducir un puerto de unidad de trabajo o cambiar el contrato de commit de los repositorios: rediseño, no se hizo. Efecto si falla a mitad: el código queda consumido y el usuario pide uno nuevo; no hay pérdida de datos. Pendiente de decisión.
6. **Inconsistencia con recuperación:** la recuperación de contraseña sigue exigiendo solo ≥8 caracteres (decisión D del padre). La decide el dueño.
7. **Template HTML de email:** los emails de cambio son texto plano; el template HTML de recuperación no se replicó. Lo decide el dueño.
