"""src/infrastructure/produccion/adaptador_ssh.py — Adaptador de solo lectura contra producción vía `ssh`.

Solo ejecuta consultas nombradas de la allowlist, con la sesión en READ ONLY, y el SQL viaja por stdin
(nunca en la línea de comando). Comandos remotos fijos; cualquier falla de ssh o mysql es ruidosa.
"""

import re
import subprocess
from collections.abc import Callable

from src.application.ports.auditoria_produccion_port import AuditoriaProduccionPort
from src.infrastructure.produccion.consultas_allowlist import CONSULTAS, validar_solo_lectura
from src.infrastructure.produccion.parseo_salida import parse_entorno, parse_tsv

HOST_POR_DEFECTO = "vps"
TIMEOUT_S = 120
_HOST_VALIDO = re.compile(r"[A-Za-z0-9_.-]+")
_CABECERA_SOLO_LECTURA = "SET SESSION TRANSACTION READ ONLY;\n"

# Credenciales desde el .env remoto (mismo patrón que el resto del proyecto); nunca desde este equipo.
_COMANDO_MYSQL = (
    "cd /var/www/datamaq-telemetry && set -a && . ./.env && set +a && "
    'mysql -h"$DB_HOST" -P"${DB_PORT:-3306}" -u"$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" --batch'
)
# Emite solo la longitud de OTP_HMAC_KEY (nunca el valor) y APP_ENV. Las comillas se quitan antes de medir.
_COMANDO_ENTORNO = (
    "cd /var/www/datamaq-telemetry && grep -E '^(OTP_HMAC_KEY|APP_ENV)=' .env "
    '| tr -d "\\"\'\\r" '
    "| awk -F= '{k=$1; v=substr($0,length(k)+2); "
    'if(k=="OTP_HMAC_KEY") print "otp_hmac_key_longitud=" length(v); else print "app_env=" v}\''
)

Ejecutor = Callable[[list[str], str, int], str]


def _ejecutar_ssh(args: list[str], stdin: str, timeout: int) -> str:
    try:
        resultado = subprocess.run(
            args,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ssh/mysql falló (código {exc.returncode}): {exc.stderr.strip()[:300]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"ssh/mysql excedió el timeout de {timeout} s") from exc
    return resultado.stdout


class AdaptadorAuditoriaProduccionSsh(AuditoriaProduccionPort):
    def __init__(self, host: str = HOST_POR_DEFECTO, ejecutor: Ejecutor = _ejecutar_ssh) -> None:
        if not _HOST_VALIDO.fullmatch(host):
            raise ValueError("host SSH inválido")
        self._host = host
        self._ejecutor = ejecutor

    def _ssh(self, comando: str) -> list[str]:
        return ["ssh", "-o", "BatchMode=yes", self._host, comando]

    def consultar(self, nombre: str) -> list[dict[str, object]]:
        if nombre not in CONSULTAS:
            raise ValueError(f"consulta no permitida: {nombre}")
        sql = CONSULTAS[nombre]
        validar_solo_lectura(sql)
        salida = self._ejecutor(self._ssh(_COMANDO_MYSQL), _CABECERA_SOLO_LECTURA + sql + ";\n", TIMEOUT_S)
        return parse_tsv(salida)

    def entorno_remoto(self) -> dict[str, object]:
        salida = self._ejecutor(self._ssh(_COMANDO_ENTORNO), "", TIMEOUT_S)
        return parse_entorno(salida)
