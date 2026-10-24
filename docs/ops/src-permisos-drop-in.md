# Drop-in: chequeo de permisos de `src/` antes de arrancar (#23)

**Estado:** referencia versionada. La unidad de systemd vive en el VPS, no en git: el dueño copia este bloque
al VPS y aplica el cambio. Ninguna sesión de código toca el VPS.

**Decisión:** fail-closed (el dueño, 2026-10-13). Si algún archivo de `src/` no es legible por el usuario del
servicio, `ExecStartPre` falla y el servicio no arranca. Así el motivo queda en `systemctl status` en vez de en
un bucle de reinicios como el de #22 (786 reinicios).

## Bloque a instalar

```ini
# /etc/systemd/system/datamaq-telemetry.service.d/src-permisos.conf
[Service]
ExecStartPre=/bin/sh -c 'test -z "$(find /var/www/datamaq-telemetry/src \( -type f ! -perm -o=r -o -type d ! -perm -o=rx \) -print -quit)"'
```

- Un `ExecStartPre` de drop-in **se suma** a los de la unidad. No hace falta resetear los existentes.
- Falla (exit ≠ 0) si `find` encuentra un archivo sin lectura para «otros» o un directorio sin `r`/`x` para «otros».
- Corre como el `User=` del servicio (`datamaq-telemetry`, ver `user.conf`), así que chequea lo mismo que el proceso.
- Alcance: solo `src/`. No mira `.env`, `.venv` ni `data/`.

## Cómo lo aplica el dueño

1. Copiar el bloque a `/etc/systemd/system/datamaq-telemetry.service.d/src-permisos.conf`.
2. Probar el chequeo sin tocar el servicio:
   `sudo -u datamaq-telemetry sh -c 'test -z "$(find /var/www/datamaq-telemetry/src \( -type f ! -perm -o=r -o -type d ! -perm -o=rx \) -print -quit)"'; echo $?`
   Debe dar `0` con `src/` sano.
3. `sudo systemctl daemon-reload`. El cambio se activa en el próximo arranque del servicio.

## Qué no cubre

- Ediciones manuales de permisos entre deploys: sí las cubre, pero solo al próximo arranque. El monitor de
  reinicios (`scripts/monitor_reinicios.sh`) avisa si el servicio entra en bucle.
- El deploy ya normaliza permisos (`scripts/deploy-server.sh`, `chmod o+r` sobre lo trackeado y aborto con rollback).
