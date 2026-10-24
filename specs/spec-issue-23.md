# Spec — Issue datamaq-automation/datamaq#23: prevenir archivos de `src/` con modo 0600

> Borrador para aprobación. Sin commit. Rama `ops/issue-23-chequeo-permisos-src` desde `origin/main`.
> Sin tocar el VPS: el cambio de unidad y la alerta los aplica el dueño.

## 1. Estado verificado

- **La unidad de systemd no está en git.** `git ls-files` no tiene ningún `.service`, `.conf` ni cron. La unidad vive en el VPS. El `drop-in` existente (`user.conf`, `limits.conf`) tampoco está en el repo (`docs/devops-mejoras-2026-09-13.md:22,90`; `AGENTS.md`).
- **Ya existe un chequeo parcial en el deploy.** `scripts/deploy-server.sh:169-170` normaliza permisos con `chmod o+r` sobre lo trackeado. `:190-199` aborta con rollback si queda un archivo trackeado sin lectura para el usuario del servicio. Cubre el deploy, no las ediciones manuales ni los reinicios.
- **El servicio corre como `datamaq-telemetry`** (`AGENTS.md`, drop-in `user.conf`), no como `datamaq`. El chequeo tiene que ejecutarse como ese usuario.
- **`scripts/deploy-server.sh`** reinicia con `systemctl restart` (`:105`, `:252`). `scripts/logs.sh` ya usa `datamaq-telemetry.service` como nombre.

## 2. Punto 3 — `ExecStartPre` que valida lectura en `src/`

**Dónde vive:** drop-in nuevo en el VPS, no en el repo. Como no hay unidad en git, el bloque exacto es:

```ini
# /etc/systemd/system/datamaq-telemetry.service.d/src-permisos.conf
[Service]
ExecStartPre=/bin/sh -c 'test -z "$(find /var/www/datamaq-telemetry/src \( -type f ! -perm -o=r -o -type d ! -perm -o=rx \) -print -quit)"'
```

- Un `ExecStartPre` en un drop-in **se suma** a los de la unidad. Si la unidad ya tiene uno, no hace falta resetearlo.
- Falla (exit ≠ 0) si `find` encuentra un archivo sin lectura para otros, o un directorio sin `r`/`x` para otros. Eso cubre la causa de #22 (archivos 0600 en `src/`).
- Corre como el `User=` del servicio, así que el chequeo es el mismo que el del proceso.
- Alcance: solo `src/`. No mira `.env`, `.venv` ni `data/`, como pide la restricción del issue.
- Para probarlo sin tocar el servicio, el dueño puede correr el mismo comando como `datamaq-telemetry`: `sudo -u datamaq-telemetry sh -c '...'`. Yo no lo ejecuto.

**Versionado en el repo:** propongo guardar el bloque en `docs/ops/src-permisos-drop-in.md` (documentación, sin unidad), para que el dueño lo copie al VPS. Así el VPS sigue siendo la fuente de la unidad y el repo tiene la referencia.

## 3. Punto 4 — detección de reinicios en bucle

**Qué script:** `scripts/monitor_reinicios.sh` en el repo. Se versiona, pero no se ejecuta desde el deploy.

**Fuente:** `systemctl show datamaq-telemetry -p NRestarts` no sirve sola. `NRestarts` cuenta reinicios automáticos y su valor cambia con arranques manuales. Propongo leer el journal:

```bash
journalctl -u datamaq-telemetry --since "10 min ago" | grep -c "Scheduled restart job"
```

Cuenta reinicios automáticos de systemd (`Restart=`), que es lo que hizo el bucle de #22 (786 reinicios).

**Dónde corre:** cron en el VPS, cada 5 min, con un usuario que pueda leer el journal (grupo `systemd-journal` o `adm`). No como root. Lo instala el dueño.

**Umbral propuesto:** ≥ 3 reinicios automáticos en 10 min → alerta. Un reinicio aislado (deploy, reboot) no alerta.

**Canal de alerta:** pendiente de decisión. Opciones: `logger -p user.crit` (queda en journal/syslog) o email. El repo no tiene un canal definido.

**Fuera del deploy:** el monitor no corre en `scripts/deploy-server.sh`. El deploy no debe depender del estado del servicio que está desplegando.

## 4. Preguntas para el dueño

1. **Si el chequeo de `src/` falla, ¿qué pasa?**
   - (a) **Fail-closed (recomendado en este spec):** `ExecStartPre` falla y el servicio no arranca. Queda caído, pero con el motivo claro en `systemctl status`, sin el bucle de reinicios de #22.
   - (b) **Fail-open:** el chequeo solo avisa y el servicio arranca igual. Pero en #22 el servicio entró en bucle porque el código no se podía leer: arrancar con archivos sin lectura probablemente reproduce el bucle sin la alerta inmediata.
   - Mi recomendación es (a), porque (b) deja el mismo bucle sin resolver. La decisión es tuya: si el servicio caído en producción es un costo que no querés pagar, (b) es la alternativa, sabiendo que no evita el bucle.
2. **Canal de alerta:** ¿`logger` (journal) alcanza, o querés email?
3. **Umbral:** ¿3 reinicios en 10 min te parece bien?

## 5. Matriz de verificación (local)

| # | Qué | Cómo |
|---|---|---|
| V1 | El script de monitoreo cuenta bien | test con journal simulado: 0, 2 y 3 reinicios → alerta solo en 3 |
| V2 | El bloque del drop-in detecta un archivo 0600 | `test` en un árbol temporal con un archivo `chmod 600` → exit ≠ 0 |
| V3 | El bloque pasa con `src/` legible | mismo árbol con permisos normales → exit 0 |

Gauntlet local: `APP_ENV=test ./scripts/pre-push.sh`.

## 6. Qué no se hace

- No se toca el VPS ni se usan credenciales.
- No se hace push ni PR.
- No se cambia `datamaq-data`, `R:180,S:-120` ni el marcado del 369.
