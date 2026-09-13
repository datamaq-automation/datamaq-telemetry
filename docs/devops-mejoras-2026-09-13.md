# Plan de Mejoras DevOps — 2026-09-13

> **Origen:** el pipeline `CD Deploy` estuvo roto ~14 horas (2026-09-13 00:31–14:19 UTC) sin que
> nadie lo notara, por `scripts/.env.deploy` commiteado con `DEPLOY_SSH_USER=root` (ver
> `docs/adr-001-no-redis-cache.md` para el contexto de la sesión completa; el detalle del
> incidente vive en el mensaje del commit `e216396`).
>
> **Estado:** aprobado en su totalidad. Algunos ítems dependen de datos que todavía no están
> disponibles (webhook, destino de backup) o de una decisión de presupuesto (staging) — quedan
> documentados, no bloquean el resto.

## Resumen

| # | Ítem | Estado | Vive en |
|---|---|---|---|
| D-1 | Required reviewers en Environment `production` | ❌ No disponible en este plan de GitHub | — |
| D-2 | Guard anti-`.env` commiteado | ✅ Hecho | `scripts/guard_secrets.sh`, CI, pre-push |
| D-3 | Alerta de deploy fallido a un canal | ⏸ Pendiente de un webhook (Slack/Discord/Telegram) | — |
| D-4 | Ambiente de staging | ⏸ Pendiente de decisión de infra/presupuesto | — |
| D-5 | Backup + stop antes de migrar, en el propio CD | ⏸ Depende de D-4 | — |
| D-6 | Backup de la base fuera del VPS actual | ⏸ Pendiente de un destino | — |
| D-7 | Logs centralizados con retención larga | ⏸ Pendiente de un destino | — |
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

## Pendientes con dato faltante

- **D-3** (alerta de deploy fallido): falta una URL de webhook real.
- **D-6** (backup fuera del host): falta definir destino (otro VPS, bucket, etc.).
- **D-7** (logs centralizados): falta definir destino/herramienta.
- **D-4 / D-5** (staging + backup-antes-de-migrar en el CD): decisión de infra/presupuesto, en
  espera.
