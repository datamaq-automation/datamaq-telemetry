"""tests/unit/test_comandos_allowlist.py — allowlist de comandos remotos de solo lectura (auditoría de producción)."""

import pytest

from src.infrastructure.produccion.adaptador_ssh import AdaptadorAuditoriaProduccionSsh
from src.infrastructure.produccion.comandos_allowlist import (
    COMANDOS_REMOTOS,
    comando_permitido,
    validar_comando_solo_lectura,
)


class _EjecutorFalso:
    def __init__(self, stdout: str = "") -> None:
        self.stdout = stdout
        self.llamadas: list[tuple[list[str], str, int]] = []

    def __call__(self, args: list[str], stdin: str, timeout: int) -> str:
        self.llamadas.append((args, stdin, timeout))
        return self.stdout


# --- Comandos esperados: texto exacto (cualquier cambio debe ser deliberado) ---


def test_comandos_de_la_allowlist_son_exactamente_los_acordados():
    assert COMANDOS_REMOTOS["version_desplegada"].comando == (
        "sudo -u datamaq git -C /var/www/datamaq-telemetry log --oneline -1"
    )
    assert COMANDOS_REMOTOS["servicio_backend_activo"].comando == "systemctl is-active datamaq-telemetry.service"
    assert COMANDOS_REMOTOS["health_local"].comando == "curl -fsS http://127.0.0.1:8885/health"


# --- Cada comando documentado y válido ---


@pytest.mark.parametrize("nombre", sorted(COMANDOS_REMOTOS))
def test_cada_comando_tiene_proposito_y_salida_esperada(nombre: str):
    entrada = COMANDOS_REMOTOS[nombre]
    assert entrada.proposito.strip()
    assert entrada.salida_esperada.strip()


@pytest.mark.parametrize("nombre", sorted(COMANDOS_REMOTOS))
def test_cada_comando_de_la_allowlist_pasa_la_validacion_de_solo_lectura(nombre: str):
    validar_comando_solo_lectura(COMANDOS_REMOTOS[nombre].comando)  # no lanza


# --- Ningún comando de escritura entra en la allowlist ---


@pytest.mark.parametrize(
    "comando",
    [
        "sudo -u datamaq git -C /var/www/datamaq-telemetry pull --ff-only",
        "sudo -u datamaq git -C /var/www/datamaq-telemetry reset --hard HEAD",
        "sudo systemctl restart datamaq-telemetry.service",
        "sudo systemctl stop datamaq-telemetry.service",
        "systemctl start datamaq-telemetry.service",
        "systemctl daemon-reload",
        "rm -rf /var/www/datamaq-telemetry",
        "sed -i 's/a/b/' /var/www/datamaq-telemetry/.env",
        "cat /var/www/datamaq-telemetry/.env > /tmp/x",
        "curl -X POST http://127.0.0.1:8885/health",
        "curl -d 'x=1' http://127.0.0.1:8885/health",
        "curl -o /tmp/salida http://127.0.0.1:8885/health",
        "curl --output /tmp/salida http://127.0.0.1:8885/health",
        "curl -T archivo http://127.0.0.1:8885/health",
        "echo x | tee /tmp/y",
        "pip install algo",
        "mv a b",
    ],
)
def test_comando_de_escritura_se_rechaza(comando: str):
    with pytest.raises(ValueError):
        validar_comando_solo_lectura(comando)


@pytest.mark.parametrize(
    "comando",
    [
        "curl -fsS http://127.0.0.1:8885/health; rm -rf /",
        "curl -fsS http://127.0.0.1:8885/health && id",
        "systemctl is-active datamaq-telemetry.service | sh",
        "git log > /tmp/x",
        "git log $(id)",
        "git log `id`",
        "git log\nrm -rf /",
        "",
        "   ",
    ],
)
def test_encadenamiento_redireccion_y_sustitucion_se_rechazan(comando: str):
    with pytest.raises(ValueError):
        validar_comando_solo_lectura(comando)


def test_ningun_comando_de_la_allowlist_contiene_palabras_de_escritura():
    from src.infrastructure.produccion.comandos_allowlist import _PALABRAS_DE_ESCRITURA

    for nombre, entrada in COMANDOS_REMOTOS.items():
        tokens = set(entrada.comando.split())
        assert not (tokens & _PALABRAS_DE_ESCRITURA), nombre


# --- Acceso por nombre: fuera de la lista no se ejecuta nada ---


def test_nombre_fuera_de_la_allowlist_no_se_ejecuta():
    with pytest.raises(ValueError, match="no permitido"):
        comando_permitido("reiniciar_backend")


def test_adaptador_rechaza_nombre_fuera_de_la_allowlist_sin_llamar_a_ssh():
    ejecutor = _EjecutorFalso()
    adaptador = AdaptadorAuditoriaProduccionSsh(ejecutor=ejecutor)
    with pytest.raises(ValueError, match="no permitido"):
        adaptador.ejecutar_comando("rm -rf /")
    assert ejecutor.llamadas == []


# --- Adaptador: el comando fijo viaja por ssh y la salida se devuelve sin saltos de línea finales ---


def test_adaptador_envia_el_comando_fijo_por_ssh_y_devuelve_su_salida():
    ejecutor = _EjecutorFalso(stdout="active\n")
    adaptador = AdaptadorAuditoriaProduccionSsh(ejecutor=ejecutor)
    salida = adaptador.ejecutar_comando("servicio_backend_activo")

    args, stdin, timeout = ejecutor.llamadas[0]
    assert args[:4] == ["ssh", "-o", "BatchMode=yes", "vps"]
    assert args[-1] == COMANDOS_REMOTOS["servicio_backend_activo"].comando
    assert stdin == ""
    assert timeout > 0
    assert salida == "active"
