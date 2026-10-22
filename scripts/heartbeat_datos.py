#!/usr/bin/env python3
"""scripts/heartbeat_datos.py — Heartbeat de datos (D2, decisions/2026-10-11_consultas-bloqueantes-dueno.md).

Consulta con el usuario de solo lectura `datamaq_ro` los minutos desde la última fila de `telemetry_instantaneous`.
Si son menos de UMBRAL_MINUTOS, manda el ping de "todo bien" a healthchecks.io; si no, el ping de falla.
Si la consulta falla o la tabla está vacía, manda el ping de falla.

Secretos (nunca en el repo, nunca en logs):
- La URL del ping vive en el archivo HEARTBEAT_PING_URL_FILE del VPS (por defecto /root/.datamaq_heartbeat_url).
- Las credenciales de la base van en el defaults-file HEARTBEAT_MYSQL_CNF (por defecto /root/.datamaq_ro.cnf).
  La contraseña nunca va en argv: `mysql --defaults-file` la lee del archivo.

Códigos de salida: 0 = dato fresco y ping enviado; 1 = dato viejo, vacío o consulta fallida, con ping de falla
enviado; 2 = no se pudo leer la URL del ping; 3 = el ping no llegó a healthchecks.io.
"""

from __future__ import annotations

import os
import subprocess
import sys
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path

UMBRAL_MINUTOS = 15
BASE_DE_DATOS = "datamaq_telemetry"
USUARIO_ESPERADO = "datamaq_ro@"
CNF_POR_DEFECTO = "/root/.datamaq_ro.cnf"
URL_POR_DEFECTO = "/root/.datamaq_heartbeat_url"
TIMEOUT_CONSULTA = 60
TIMEOUT_HTTP = 10
SQL = "SELECT CURRENT_USER(), TIMESTAMPDIFF(MINUTE, MAX(recorded_at), UTC_TIMESTAMP()) FROM telemetry_instantaneous"


class ErrorHeartbeat(Exception):
    """Fallo controlado del heartbeat. Su mensaje no contiene secretos."""


def consultar_minutos(cnf: str) -> int | None:
    """Minutos desde la última fila de telemetry_instantaneous, o None si la tabla está vacía."""
    resultado = subprocess.run(
        ["mysql", f"--defaults-file={cnf}", "-N", "-B", BASE_DE_DATOS, "-e", SQL],
        capture_output=True,
        text=True,
        timeout=TIMEOUT_CONSULTA,
        check=False,
    )
    if resultado.returncode != 0:
        raise ErrorHeartbeat(f"mysql terminó con código {resultado.returncode}")
    usuario, _, minutos = resultado.stdout.strip().partition("\t")
    if not usuario.startswith(USUARIO_ESPERADO):
        raise ErrorHeartbeat(f"la consulta corrió como {usuario.split('@')[0]}, no como datamaq_ro")
    if minutos in ("", "NULL"):
        return None
    return int(minutos)


def esta_vivo(minutos: int | None) -> bool:
    """True si hay una fila reciente. Sin filas (None) cuenta como falla."""
    return minutos is not None and minutos < UMBRAL_MINUTOS


def leer_url_ping(ruta: str) -> str:
    url = Path(ruta).read_text(encoding="utf-8").strip()
    if not url.startswith("https://"):
        raise ErrorHeartbeat("el archivo de la URL no contiene una URL https")
    return url


def enviar_ping(url: str, falla: bool) -> None:
    """GET al ping de healthchecks.io. Con falla, usa la convención de healthchecks.io: URL + '/fail'."""
    destino = f"{url}/fail" if falla else url
    with urllib.request.urlopen(destino, timeout=TIMEOUT_HTTP) as respuesta:
        if respuesta.status != 200:
            raise ErrorHeartbeat(f"el ping respondió HTTP {respuesta.status}")


def main(
    env: Mapping[str, str] = os.environ,
    consultar: Callable[[str], int | None] = consultar_minutos,
    enviar: Callable[[str, bool], None] = enviar_ping,
) -> int:
    cnf = env.get("HEARTBEAT_MYSQL_CNF", CNF_POR_DEFECTO)
    ruta_url = env.get("HEARTBEAT_PING_URL_FILE", URL_POR_DEFECTO)
    try:
        url = leer_url_ping(ruta_url)
    except (OSError, ErrorHeartbeat) as exc:
        print(f"heartbeat: no se pudo leer la URL del ping ({type(exc).__name__})", file=sys.stderr)
        return 2

    try:
        minutos = consultar(cnf)
        vivo = esta_vivo(minutos)
        motivo = "sin filas en telemetry_instantaneous" if minutos is None else f"{minutos} min desde la última fila"
    except (ErrorHeartbeat, OSError, subprocess.TimeoutExpired) as exc:
        vivo = False
        motivo = f"consulta fallida ({type(exc).__name__}: {exc})"

    print(f"heartbeat: {'OK' if vivo else 'FALLA'} ({motivo})")
    try:
        enviar(url, not vivo)
    except (OSError, ErrorHeartbeat) as exc:
        print(f"heartbeat: el ping no llegó ({type(exc).__name__})", file=sys.stderr)
        return 3
    return 0 if vivo else 1


if __name__ == "__main__":
    sys.exit(main())
