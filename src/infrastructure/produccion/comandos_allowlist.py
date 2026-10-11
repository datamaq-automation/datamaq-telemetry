"""src/infrastructure/produccion/comandos_allowlist.py — Allowlist cerrada de comandos remotos de solo lectura.

Cada entrada es un comando fijo con su propósito y su salida esperada. Ninguno escribe, reinicia, borra ni
descarga nada: `validar_comando_solo_lectura` lo verifica y los tests lo recorren entero. No hay forma de
ejecutar un comando que no esté aquí: el adaptador acepta solo nombres de esta lista.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class ComandoRemoto:
    comando: str
    proposito: str
    salida_esperada: str


COMANDOS_REMOTOS: Mapping[str, ComandoRemoto] = MappingProxyType(
    {
        "version_desplegada": ComandoRemoto(
            comando="sudo -u datamaq git -C /var/www/datamaq-telemetry log --oneline -1",
            proposito=(
                "Commit desplegado en el VPS. Git corre como el usuario datamaq, nunca como root, "
                "para no romper el ownership del repo."
            ),
            salida_esperada="Una línea: hash corto y asunto del commit, por ejemplo '089f2ef Merge pull request #4 ...'.",
        ),
        "servicio_backend_activo": ComandoRemoto(
            comando="systemctl is-active datamaq-telemetry.service",
            proposito="Estado systemd del backend (API y worker MQTT). Nombre por defecto de DEPLOY_SERVICE_NAME.",
            salida_esperada="Una palabra: 'active'. Otros valores ('inactive', 'failed', 'activating') son una alerta.",
        ),
        "health_local": ComandoRemoto(
            comando="curl -fsS http://127.0.0.1:8885/health",
            proposito=(
                "Health check HTTP del backend desde el propio VPS (loopback, sin credenciales). "
                "Mismo endpoint que usa deploy-server.sh."
            ),
            salida_esperada="Cuerpo JSON de /health con código 200. curl -f sale con error si el código es 400 o más.",
        ),
    }
)

# Palabras que vuelven escritura o ejecución arbitraria cualquier comando de esta lista.
_PALABRAS_DE_ESCRITURA: frozenset[str] = frozenset(
    {
        "chmod",
        "chown",
        "cp",
        "dd",
        "daemon-reload",
        "disable",
        "enable",
        "fetch",
        "install",
        "kill",
        "ln",
        "mkdir",
        "mv",
        "npm",
        "pip",
        "pull",
        "push",
        "reset",
        "restart",
        "rm",
        "sed",
        "start",
        "stop",
        "tee",
        "touch",
        "truncate",
        "uv",
    }
)
# Opciones de curl que escriben archivos o envían datos.
_OPCIONES_DE_ESCRITURA: frozenset[str] = frozenset({"-d", "-F", "-o", "-O", "-T", "-X"})
_CARACTERES_DE_SHELL: frozenset[str] = frozenset(";&|<>`$\\\n\r")


def validar_comando_solo_lectura(comando: str) -> None:
    """Lanza ValueError si el comando encadena otros, redirige, sustituye o escribe."""
    if not comando.strip():
        raise ValueError("comando vacío")
    if _CARACTERES_DE_SHELL & set(comando):
        raise ValueError("el comando contiene operadores de shell no permitidos")
    tokens = comando.split()
    prohibidas = sorted(set(tokens) & _PALABRAS_DE_ESCRITURA)
    if prohibidas:
        raise ValueError(f"el comando contiene palabras de escritura: {', '.join(prohibidas)}")
    if any(t in _OPCIONES_DE_ESCRITURA or t.startswith("--output") for t in tokens):
        raise ValueError("el comando contiene opciones que escriben o envían datos")


def comando_permitido(nombre: str) -> str:
    """Devuelve el comando fijo de la allowlist, validado. Lanza ValueError si el nombre no está."""
    if nombre not in COMANDOS_REMOTOS:
        raise ValueError(f"comando no permitido: {nombre}")
    comando = COMANDOS_REMOTOS[nombre].comando
    validar_comando_solo_lectura(comando)
    return comando
