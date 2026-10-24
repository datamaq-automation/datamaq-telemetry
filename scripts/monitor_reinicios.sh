#!/usr/bin/env bash
# ==============================================================================
# Detecta reinicios automáticos en bucle del servicio datamaq-telemetry (#23).
# ==============================================================================
# Cuenta en el journal los "Scheduled restart job" (reinicios por Restart=) dentro
# de la ventana. Un reinicio aislado (deploy, reboot) no alerta.
#
# Uso (cron del VPS, cada 5 min, usuario con acceso al journal: grupo adm o
# systemd-journal, nunca root):
#   scripts/monitor_reinicios.sh
#
# Variables (todas opcionales; los valores por defecto son los de producción):
#   MONITOR_UNIDAD       unidad a vigilar            (datamaq-telemetry.service)
#   MONITOR_VENTANA      ventana de journalctl       ("10 min ago")
#   MONITOR_UMBRAL       reinicios que disparan      (3)
#   MONITOR_JOURNALCTL   comando de journal          (journalctl)
#   MONITOR_LOGGER       comando de alerta           (logger)
#
# Salida: 0 sin alerta; 1 con alerta (queda en stderr y en syslog como user.crit).
# ==============================================================================
set -eu

UNIDAD="${MONITOR_UNIDAD:-datamaq-telemetry.service}"
VENTANA="${MONITOR_VENTANA:-10 min ago}"
UMBRAL="${MONITOR_UMBRAL:-3}"
JOURNALCTL_CMD="${MONITOR_JOURNALCTL:-journalctl}"
LOGGER_CMD="${MONITOR_LOGGER:-logger}"

# grep -c sale con 1 si no hay coincidencias: `|| true` conserva el "0".
reinicios=$("$JOURNALCTL_CMD" -u "$UNIDAD" --since "$VENTANA" --no-pager 2>/dev/null \
    | grep -c "Scheduled restart job" || true)

if [ "$reinicios" -ge "$UMBRAL" ]; then
    mensaje="$UNIDAD: $reinicios reinicios automáticos en '$VENTANA' (umbral $UMBRAL). Posible bucle de reinicios."
    echo "ALERTA: $mensaje" >&2
    "$LOGGER_CMD" -p user.crit -t datamaq-monitor "$mensaje" 2>/dev/null || true
    exit 1
fi

echo "OK: $reinicios reinicios automáticos en '$VENTANA' (umbral $UMBRAL)"
