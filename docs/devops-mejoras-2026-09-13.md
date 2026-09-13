# Plan de Mejoras DevOps — 2026-09-13

> **Origen:** el pipeline `CD Deploy` estuvo roto ~14 horas (2026-09-13 00:31–14:19 UTC) sin que
> nadie lo notara, por `scripts/.env.deploy` commiteado con `DEPLOY_SSH_USER=root` (ver
> `docs/adr-001-no-redis-cache.md` para el contexto de la sesión completa; el detalle del
> incidente vive en el mensaje del commit `e216396`).
>
> **Estado:** aprobado en su totalidad y **cerrado**: 8 de 9 ítems hechos, D-1 descartado por
> límite del plan de GitHub (sin alternativa aplicada, se mantuvo el auto-deploy).

## Resumen

| # | Ítem | Estado | Vive en |
|---|---|---|---|
| D-1 | Required reviewers en Environment `production` | ❌ No disponible en este plan de GitHub | — |
| D-2 | Guard anti-`.env` commiteado | ✅ Hecho | `scripts/guard_secrets.sh`, CI, pre-push |
| D-3 | Alerta de deploy fallido a un canal | ✅ Hecho — Telegram | `.github/workflows/deploy.yml` (step final, `if: failure()`) |
| D-4 | Ambiente de staging | ✅ Hecho — PC local de escritorio, no el VPS (ver nota) | `~/backups/datamaq-telemetry/refresh_staging.sh` (no está en git, es de esta PC) |
| D-5 | Backup + stop antes de migrar, en el propio CD | ✅ Hecho | `scripts/deploy-server.sh` |
| D-6 | Backup de la base fuera del VPS actual | ✅ Hecho — PC local de escritorio, timer diario 04:30 | `~/backups/datamaq-telemetry/backup_diario.sh` (no está en git) |
| D-7 | Logs centralizados con retención larga | ✅ Hecho — PC local, timer diario 04:45, 30 días de retención | `~/backups/datamaq-telemetry/logs_diario.sh` (no está en git) |
| D-8 | Aislamiento por cgroups del servicio | ✅ Hecho | VPS: `/etc/systemd/system/datamaq-telemetry.service.d/limits.conf` (no está en git) |
| D-9 | Actions sobre Node 24 (sacar warning de Node 20) | ✅ Hecho | `.github/workflows/*.yml` |

## D-1 · Required reviewers — evaluado y descartado por ahora

Intentado vía `gh api repos/.../environments/production --method PUT -f reviewers[][type]=User`:

```
422 — Failed to create the environment protection rule.
Please ensure the billing plan supports the required reviewers protection rule.
```

Se probó también `wait_timer` (alternativa sin reviewer, solo demora) — mismo bloqueo de plan.
Ninguna protección nativa de Environment está disponible hoy. La alternativa de costo cero (sacar
el trigger automático `workflow_run` y dejar el deploy solo por `workflow_dispatch`) se evaluó y
**se descartó**: se decidió mantener el auto-deploy. Revisar si en algún momento se evalúa un
upgrade de plan de GitHub (Team/Enterprise habilitan esto).

## D-2 · Guard anti-`.env` commiteado

`scripts/guard_secrets.sh` bloquea cualquier archivo `.env`/`.env.*` trackeado en git que no sea
`.example`/`.sample`. Corre en dos lugares:

- **Local:** Stage 0 de `scripts/pre-push.sh` (vía `.githooks/pre-push`).
- **CI:** primer step de `.github/workflows/ci.yml`, antes de instalar dependencias — server-side,
  no evitable con `git push --no-verify` ni desde una máquina sin el hook configurado
  (`git config core.hooksPath .githooks`).

## D-4 · Staging — PC local, no "el mismo VPS con un medidor"

Se evaluó y **se descartó** la alternativa de usar el propio VPS de producción como staging
(acotado a un solo medidor). Dos motivos, en orden de importancia:

1. **Cero aislamiento real.** Un error de una migración de prueba (bloqueo de tabla, disco lleno,
   MySQL caído) pasa en el mismo MySQL, mismo disco, misma RAM que usa producción — exactamente lo
   que un staging existe para evitar. La migración de WP2 de hoy tuvo una condición de carrera real
   que, de haber corrido "en el mismo VPS", habría afectado el servicio real mientras se investigaba.
2. **Acotar a un solo medidor esconde justo los problemas que importan.** Los bugs de hoy (WP1 con
   ~87 000 filas por consulta, WP2 con 123 000 filas duplicadas) aparecen por volumen y por
   varios medidores interactuando — un dataset de un solo medidor da falsa confianza.

**Lo que se implementó en cambio:** la PC de escritorio de Agustín ya tenía una base MySQL local
con datos reales de los 5 medidores (la que se usó para ensayar la migración de WP2 durante la
sesión). Cumple los dos requisitos de un staging — está genuinamente aislada del VPS (un error acá
no lo toca) y tiene datos a escala real, no un subconjunto — y no cuesta un servidor nuevo.

- `~/backups/datamaq-telemetry/refresh_staging.sh`: restaura la base local desde el backup más
  reciente de D-6 (o uno puntual, como argumento). Deja la base al mismo estado de migraciones que
  el VPS en el momento del backup — verificado hoy: `m7n8o9p0q1r2 (head)` en ambos lados.
- Flujo para ensayar una migración: `bash refresh_staging.sh` → `DATABASE_URL=... alembic upgrade head`
  contra la base local → si sale limpio, recién ahí correr contra el VPS real.
- **No versionado**: estos tres scripts (`backup_diario.sh`, `logs_diario.sh`,
  `refresh_staging.sh`) viven en `~/backups/datamaq-telemetry/` de esta PC, fuera del repo — son
  configuración de esta máquina, no del proyecto. Si en algún momento se decide que otra persona
  también necesite este flujo, conviene versionarlos en `scripts/` con las credenciales por
  variable de entorno en vez de hardcodeadas.

**Límite de este staging, dicho explícitamente:** el refresh es manual, no corre servicio
`datamaq-telemetry` real contra la base local (solo se prueban migraciones de Alembic, no
comportamiento end-to-end de la API), y depende de que la PC esté prendida y con red hacia el VPS
para refrescarse. Es una mejora real sobre "ensayar a mano cada vez", no un staging de nivel
producción.

## D-8 · Aislamiento por cgroups

Aplicado directamente en el VPS (no versionado — es configuración de la máquina, no del repo):

```
/etc/systemd/system/datamaq-telemetry.service.d/limits.conf
[Service]
MemoryHigh=384M
MemoryMax=512M
CPUQuota=150%
```

Uso real medido antes de aplicar: ~123 MB RAM, ~3% CPU (2 vCPU disponibles) — los límites son un
techo de seguridad generoso (4× la RAM en uso), no un ajuste fino de capacidad. Verificado con
`systemctl daemon-reload && systemctl restart datamaq-telemetry`: servicio activo, `GET /health`
→ 200 tras el reinicio.

**Pendiente si se quiere ir más lejos:** aplicar el mismo patrón a `eitec.service`,
`isftn199.service` y los demás servicios del VPS — hoy solo `datamaq-telemetry` tiene techo.

## D-9 · Actions actualizadas

- `actions/checkout`: `v4` → `v7.0.1` (declara `using: node24` nativo).
- `webfactory/ssh-agent`: `v0.9.0` → `v0.10.0` (ídem).

Inputs verificados sin cambios rotos para el uso actual del repo.

## D-3 · Alerta de deploy fallido por Telegram

Step final de `.github/workflows/deploy.yml`, `if: failure()` — se dispara solo si `Deploy` (el
step anterior) falla, con el commit, quién lo disparó y el link al run.

Bot reutilizado, no uno nuevo: `@datamaq_bot`, ya usado por `datamaq-hub` y `www-datamaq`
("Watchdog & Alertas" / "Notificaciones & Alertas") con el mismo `chat_id`. Token y `chat_id`
extraídos de `/var/www/datamaq-hub/.env` (root en el VPS), seteados como secrets del Environment
`production` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`), nunca escritos en el repo. Probado antes
de conectarlo: mensaje de prueba entregado (`ok: true`) al chat privado de Agustín.

## D-5 · Backup + stop antes de migrar, dentro del propio CD

`scripts/deploy-server.sh` cambió de "migrar con el servicio corriendo, después reiniciar" a:

1. `mysqldump --add-drop-table` de toda la base a `/tmp/datamaq-telemetry-pre-migracion/`
   (retención corta: los últimos 5 dumps, solo para el rollback inmediato de este deploy — no
   reemplaza el backup diario con retención larga fuera del VPS de D-6).
2. **Detener el servicio antes de `alembic upgrade head`** — antes migraba con el proceso vivo,
   que es exactamente la condición de carrera que causó el problema de WP2 durante la sesión
   (escrituras concurrentes mientras se creaba un índice único).
3. Si la migración falla: restaura la base desde el dump y el código al commit anterior, arranca
   el servicio viejo.
4. Si la migración sale bien pero el health-check post-deploy falla: **también restaura la base**,
   no solo el código — antes el rollback por health-check solo revertía código y dependencias,
   dejando código viejo corriendo contra un esquema ya migrado si la migración había sido la causa
   real de la falla.

Credenciales: las mismas que ya usa la aplicación (`source .env` en el propio VPS, usuario
`datamaq`) — no hizo falta ningún secret nuevo. Ensayado antes de aplicar: backup + restore
sobre la base real, sobre sí misma (inofensivo), confirmando que el usuario `datamaq` tiene los
permisos que el script asume.

**Trade-off aceptado a propósito:** todo deploy ahora tiene una ventana de downtime real (stop →
migrar → start), no el reinicio casi instantáneo de antes — incluso para pushes sin cambios de
esquema (`alembic upgrade head` sobre una base ya al día es casi inmediato, pero igual pasa por
detener y levantar el servicio). Se prefirió simplicidad y corrección sobre optimizar para el
caso común de "no hay migración nueva".
