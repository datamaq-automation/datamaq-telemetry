# Spec — Despliegue del backend en `api-dev.datamaq.com.ar`

> Borrador para aprobación del padre (`datamaq-da`). **Solo spec: sin código, sin VPS, sin push.**
> Untracked. Ramas: ninguna se publica hasta que exista el entorno dev (`decisions/2026-10-13_sin-publicar-hasta-entorno-dev.md`).
> Cualquier cambio en el VPS lo ejecuta el dueño, nunca esta sesión.

## 1. Objetivo y contexto

Tener una instancia del backend `datamaq-telemetry` en `api-dev.datamaq.com.ar`, separada de producción, para
validar cambios antes de que lleguen a `main` (que despliega solo a producción).

**Datos del relevamiento** (aplicados por el dueño en el VPS; esta sesión **no los verificó en el servidor**):

| Recurso | Valor |
|---|---|
| Usuario de servicio | `datamaq-dev`, sin login, home `/var/www/datamaq-dev`, modo `0700` |
| Base de datos | `datamaq_dev`, con usuario propio |
| Credenciales DB | `/var/www/datamaq-dev/.mysql_credentials` (modo `600`). **No se leen ni se copian.** |
| Certificado TLS | `/etc/letsencrypt/live/api-dev.datamaq.com.ar/` (ya emitido) |
| Puertos internos libres | `8005`–`8010` y `8013` |
| Ingesta MQTT | **apagada en dev** (decisión del dueño) |

**Verificado en el repo (esta sesión):**
- `API_PORT` default `8885` (`src/infrastructure/settings/config.py:50`); `src/main.py:14` levanta uvicorn con `settings.API_PORT`. Hay que fijarlo por env (`API_PORT=8005`).
- **No existe un flag para apagar MQTT.** `src/infrastructure/fastapi/server.py:359` llama `mqtt_listener.start()` sin condición. Apagar la ingesta en dev requiere un cambio de código (ver §4, decisión D2).
- No hay rama `develop`. `deploy.yml:9` dispara solo en `push` a `main`.
- `scripts/deploy-server.sh` está parametrizado por env (`DEPLOY_SSH_HOST`, `DEPLOY_REMOTE_DIR`, `DEPLOY_SERVICE_NAME`, `DEPLOY_HEALTH_URL`), pero contiene lógica de producción: corre migraciones contra la base del servidor, hace rollback y usa `/tmp` para backup. No conviene reutilizarlo para dev sin revisión (ver D1).
- El arranque verifica la consistencia de organizaciones contra el YAML de `data/` (`src/infrastructure/fastapi/server.py:337`, `verificador_consistencia.py`). **Dev necesita su propio checkout de `data/`**, o el servicio no arranca.

## 2. Decisiones

**D1 — Cómo se despliega dev (decisión del dueño, propuesta de esta spec):**
El despliegue de dev **no es el CD de producción** y no toca `deploy.yml`.
- Se crea la rama `develop` desde `main`. Los cambios a validar se integran ahí, nunca en `main`.
- Se agrega `scripts/deploy-dev.sh` (script nuevo, separado de `deploy-server.sh`). Hace: `git -C <dev>/app fetch && checkout develop && pull --ff-only`, `data/` en su propio pull, `pip sync` del `requirements.lock` en su `.venv`, `systemctl restart datamaq-dev.service` y `curl` a `/health`.
- **Guardas del script:** aborta si `DEPLOY_DEV_REMOTE_DIR` apunta a `/var/www/datamaq-telemetry` o si el servicio es `datamaq-telemetry.service`. Así no puede reiniciar producción.
- Quién lo corre: el dueño, o una sesión hija con autorización explícita del dueño en su propia ventana (regla de §1e: la autorización no se transfiere).
- Alternativa descartada: parametrizar `deploy-server.sh`. Mezcla rollback y migraciones de producción con dev y aumenta el riesgo de tocar prod.

**D2 — Ingesta MQTT apagada en dev:** hace falta un setting `MQTT_HABILITADO: bool = True` (default `True` para no cambiar producción) que gatee `mqtt_listener.start()`. Con `MQTT_HABILITADO=false` en `.env` de dev, el listener no arranca. **Requiere OK explícito del padre para el cambio de código** (fuera de esta spec).

**D3 — Perfil de la app en dev:** propuesta: `APP_ENV=production` y `DEBUG=false` en el `.env` de dev. Razón: `DEBUG=false` deja `AUTH_COOKIE_SECURE=true` (ver spec CORS) y la postura de seguridad de producción, sin cambiar código. Alternativa: `APP_ENV=development` (cookie no Secure, docs expuestos). Decide el dueño.

**D4 — Secretos separados de producción:** `API_SECRET_KEY` y `OTP_HMAC_KEY` **propios de dev**, no copiados de prod. Pregunta al dueño: ¿el `.env` de dev referencia `.mysql_credentials` o contiene las credenciales de DB directamente? Esta spec no lee el archivo.

## 3. Diseño

**Estructura en el servidor** (todo bajo el home del usuario de servicio):

```
/var/www/datamaq-dev/
├── app/          # checkout git de datamaq-telemetry, rama develop (NO el de producción)
│   ├── .venv/    # Python 3.12, sincronizado con requirements.lock
│   ├── .env      # propio de dev (ver D3, D4); el servicio lo lee
│   └── data/     # checkout propio de datamaq-data (requerido por el verificador de arranque)
└── .mysql_credentials   # ya existe, 600; no se toca
```

**Unidad systemd** `datamaq-dev.service` (archivo en el VPS, fuera de git; el bloque queda versionado en `docs/ops/`):
- `User=datamaq-dev`, `Group=datamaq-dev`, `WorkingDirectory=/var/www/datamaq-dev/app`
- `Environment=API_PORT=8005` (primer puerto libre) y `Environment=MQTT_HABILITADO=false` (si D2 se aprueba)
- `ExecStart=/var/www/datamaq-dev/app/.venv/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 8005`
- `Restart=on-failure` con `StartLimitBurst` acotado, para no repetir el bucle de #22.

**Reverse proxy (nginx)** para `api-dev.datamaq.com.ar`:
- TLS con `/etc/letsencrypt/live/api-dev.datamaq.com.ar/`.
- `proxy_pass http://127.0.0.1:8005`, con cabeceras `Upgrade`/`Connection` para `/ws/live`.
- Sin HTTP → HTTPS redirigido igual que producción.

**Base de datos:** `datamaq_dev` arranca vacía. Migraciones con `alembic upgrade head` **solo** contra `datamaq_dev`. Guarda: el script de migración aborta si `DB_NAME` no es `datamaq_dev`. Nunca `stamp` ni `upgrade` sobre una base sin `alembic_version` de producción (AGENTS, §3 de telemetría).

## 4. Matriz de verificación

| # | Qué | Cómo | Quién |
|---|---|---|---|
| V1 | `/health` responde 200 en `127.0.0.1:8005` | `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8005/health` | Dueño o hija con OK |
| V2 | Servicio con el usuario correcto | `systemctl show datamaq-dev -p User -p Group` → `datamaq-dev` | Lectura |
| V3 | Ingesta apagada | `journalctl -u datamaq-dev` no contiene `mqtt` conectando; `ss -tn` sin conexión a `8884` | Lectura |
| V4 | Base correcta | `SELECT DATABASE()` = `datamaq_dev` (usuario de solo lectura, sin tocar credenciales en el chat) | Dueño |
| V5 | HTTPS válido | `curl -sI https://api-dev.datamaq.com.ar/health` | Lectura |
| V6 | Producción intacta | `curl https://api.datamaq.com.ar/health` 200 y `systemctl is-active datamaq-telemetry` activo | Lectura |
| V7 | Gauntlet local | `APP_ENV=test ./scripts/pre-push.sh` redirigido a archivo | Local |

Pruebas automáticas nuevas: `tests/unit/test_deploy_dev.py` para las guardas de `deploy-dev.sh` (rechaza el directorio y el servicio de producción) y para la guarda de `DB_NAME` en la migración. Mismo patrón que `tests/unit/test_deploy_server.py`.

## 5. Criterios de aceptación

- `api-dev` responde por HTTPS con el certificado existente.
- El servicio corre como `datamaq-dev`, con `API_PORT` en `8005`.
- Ningún proceso de dev escribe en `datamaq`, ni en `datamaq_telemetry`, ni en `/var/www/datamaq-telemetry`.
- `deploy-dev.sh` no puede apuntar a producción (guardas probadas).
- Producción no cambia: mismo `main`, mismo servicio, mismo health.

## 6. Qué no se hace

- No se toca el VPS desde esta sesión ni se leen credenciales.
- No se modifica `deploy.yml` ni `deploy-server.sh`.
- No hay push ni PR. Las ramas quedan locales hasta el OK del padre.
- No se implementa `MQTT_HABILITADO` ni `DEBUG` sin aprobar D2/D3.

## 7. Preguntas para el dueño (vía padre)

1. **D3:** ¿dev corre con `APP_ENV=production, DEBUG=false` (recomendado) o `APP_ENV=development`?
2. **D4:** ¿el `.env` de dev contiene las credenciales de DB o las referencia desde `.mysql_credentials`?
3. **D2:** ¿aprobás el setting `MQTT_HABILITADO` para apagar la ingesta en dev?
4. **D1:** ¿aprobás `develop` + `scripts/deploy-dev.sh` separado, en vez de reutilizar `deploy-server.sh`?
5. ¿Qué rama de `datamaq-data` usa el checkout de dev: `main` o una propia?
