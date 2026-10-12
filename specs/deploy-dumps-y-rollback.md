# Deploy: dumps privados y rollback ante cualquier fallo

> **Issue:** datamaq-automation/datamaq#17 · **Rama:** `fix/issue-17-deploy-dumps-y-rollback` (desde `main` con #16)

## 1. Objetivo y Contexto

Auditoría de solo lectura del VPS (2026-10-11):

- Los dumps previos a cada deploy (`mysqldump … | gzip`) quedaban en un directorio `755` con archivos `644`. Cada dump es
  la base completa (usuarios, hashes, tokens OAuth) y el VPS tiene otros usuarios locales.
- El heredoc remoto corría con `set -e` y sin `pipefail`. Si fallaba `mysqldump`, el `| gzip` terminaba bien y quedaba
  un dump vacío o truncado. Un rollback posterior lo restauraba con `--add-drop-table`.
- Si fallaban `git` o `pip`, el script salía sin rollback.

## 2. Dominio & Puertos

No aplica: es tooling de despliegue (`scripts/deploy-server.sh`, bloque remoto que corre por ssh en el VPS).

## 3. Caso de uso & DTOs

Cambios en el heredoc remoto:

| Cambio | Detalle |
|---|---|
| `set -Eeuo pipefail` | `-E` para que el trap ERR alcance a las funciones; `pipefail` para que un `mysqldump` que falla no quede tapado por `gzip`. `.env` se carga con `set +u` y después se restaura `set -u` y se validan `DB_*` con `:?`. `GITHUB_TOKEN` y `GITHUB_REPOSITORY` se leen con `${…:-}`. |
| `umask 077` | Dumps y freeze de pip solo legibles por el usuario del deploy. |
| Directorio de dumps | `install -d -m 700`, que también corrige un directorio existente en `755` (verificado). `chmod 600` a los dumps existentes. |
| Validación del dump | Tamaño > 0, `gzip -t` y el pie `-- Dump completed` (`gzip -dc … \| tail -n 1 \|\| true`: con `pipefail`, un SIGPIPE no aborta; la integridad ya la probó `gzip -t`). Si falla, se borra el dump y se aborta **antes** de `systemctl stop`. |
| Rotación | `find -printf` + `sort` en vez de `ls -t \| tail`, que con `pipefail` abortaba si no había archivos. |
| `abortar_con_rollback` | Una función para todos los rollbacks. Empieza con `trap - ERR` y `set +e`: si una parte del propio rollback falla, no re-entra, hace el resto y avisa **"ROLLBACK INCOMPLETO"**. Siempre sale con `exit 1`: un deploy revertido nunca deja el CD en verde. Con `con_base` (migración o health): stop, restaurar el dump, código, deps y start. |
| `trap ERR` | Armado entre el guardado de `PREVIOUS_COMMIT` y el `systemctl stop`: un fallo de git, pip, `data/` o del dump revierte el código y las dependencias. La base no se tocó y el servicio sigue corriendo con el código anterior en memoria. |
| Rutas sobreescribibles | `DEPLOY_BACKUP_DIR` y `DEPLOY_DEPS_FILE`, solo para el test (por ssh no se pasan: rigen los defaults de `/tmp`). |

**Documentado, no resuelto en este bloque:**

- **Rollback de `data/`:** el rollback no revierte `datamaq-data`. Si el `git -C data pull` trajo un YAML que rompe el
  arranque, el health falla, se restauran la base y el código, y el servicio arranca con el `data/` nuevo. Para resolverlo
  habría que guardar el `HEAD` de `data/` antes del pull y hacer `git -C data reset --hard` en el rollback.
- **Paquetes nuevos:** `pip install -r <freeze anterior>` vuelve a las versiones previas, pero no desinstala los paquetes
  que agregó el lock nuevo. Quedan instalados sin uso. Para resolverlo, `pip-sync` del freeze anterior (pip-tools) o
  reconstruir el `.venv`.
- **Fallos inesperados después del stop** (por ejemplo, `systemctl start` falla fuera del camino de migración o de
  health): cortan sin rollback, como antes de #17.
- El health check solo mira `/health`.

## 4. Matriz de Pruebas (RED Suite)

`tests/unit/test_deploy_server.py` extrae el heredoc del script y lo corre con bash real y stubs en el `PATH` (git, pip,
mysqldump, mysql, sudo, sleep). No toca ninguna base, servicio ni repo.

| Test | Verifica |
|---|---|
| deploy feliz | directorio `700`, dumps (nuevo y existente) `600`, stop llamado, sin `git reset`. El dump es mayor que el buffer de un pipe, así que el pie se lee bajo `pipefail`. |
| `mysqldump` falla | exit ≠ 0, **sin stop**, `git reset --hard` al commit anterior, sin restaurar la base |
| dump sin pie | exit ≠ 0, sin stop, dump borrado |
| `pip` falla / `git` falla | exit ≠ 0, rollback de código, sin systemctl |
| el rollback falla | `ROLLBACK INCOMPLETO`, exit ≠ 0, un solo `git reset` (no re-entra) |
| migración falla / health falla | restaura base y código, start al final, exit ≠ 0 |
| con token | `fetch … main:refs/remotes/origin/main` y `merge --ff-only` (#16) |
| `set -u` | sin `GITHUB_TOKEN` o sin `GITHUB_REPOSITORY` definidos, el fallback `git pull` funciona |

Con el script anterior (solo con las rutas parametrizadas) fallan 7 de los 11 tests.

## 5. Criterios del Gauntlet

`bash -n` y `shellcheck -S warning` sin hallazgos (quedan las 2 notas informativas que ya había, fuera del heredoc).
`./scripts/pre-push.sh` en verde con `APP_ENV=test`.

## 6. Notas de implementación

- Criterio de cierre del issue (lo verifica el padre después de un deploy): directorio en `700` y dump nuevo en `600`. El
  test cubre que un `mysqldump` que falla aborta antes del stop.
- Mitigación inmediata en producción (la autoriza el dueño, fuera de esta rama):
  `chmod 700 /tmp/datamaq-telemetry-pre-migracion`. Con esta rama, el próximo deploy lo corrige solo.
