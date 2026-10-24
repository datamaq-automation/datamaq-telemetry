"""Verificación local de #23: chequeo de permisos de src/ y monitor de reinicios.

El bloque ExecStartPre se lee del propio doc versionado (docs/ops/src-permisos-drop-in.md),
para probar exactamente lo que el dueño copia al VPS, no una copia en el test.
"""

import os
import shlex
import stat
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
DOC_DROP_IN = RAIZ / "docs" / "ops" / "src-permisos-drop-in.md"
MONITOR = RAIZ / "scripts" / "monitor_reinicios.sh"
SRC_PRODUCCION = "/var/www/datamaq-telemetry/src"


def _argv_exec_start_pre() -> list[str]:
    linea = next(ln for ln in DOC_DROP_IN.read_text(encoding="utf-8").splitlines() if ln.startswith("ExecStartPre="))
    return shlex.split(linea.removeprefix("ExecStartPre="))


def _correr_chequeo(src: Path) -> int:
    argv = _argv_exec_start_pre()
    argv[-1] = argv[-1].replace(SRC_PRODUCCION, str(src))
    return subprocess.run(argv, check=False).returncode


def _arbol_src(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    (src / "domain").mkdir(parents=True)
    archivo = src / "domain" / "entities.py"
    archivo.write_text("x = 1\n", encoding="utf-8")
    archivo.chmod(0o644)
    (src / "domain").chmod(0o755)
    src.chmod(0o755)
    return src


def test_chequeo_pasa_con_src_legible(tmp_path: Path) -> None:
    src = _arbol_src(tmp_path)
    assert _correr_chequeo(src) == 0


def test_chequeo_falla_con_archivo_0600(tmp_path: Path) -> None:
    src = _arbol_src(tmp_path)
    (src / "domain" / "entities.py").chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600: lo que causó #22
    assert _correr_chequeo(src) != 0


def test_chequeo_falla_con_directorio_sin_x_para_otros(tmp_path: Path) -> None:
    src = _arbol_src(tmp_path)
    (src / "domain").chmod(0o750)
    assert _correr_chequeo(src) != 0


def test_drop_in_solo_apunta_a_src() -> None:
    argv = _argv_exec_start_pre()
    assert argv[:2] == ["/bin/sh", "-c"]
    assert SRC_PRODUCCION in argv[-1]
    assert ".env" not in argv[-1]
    assert "/datamaq-telemetry/data" not in argv[-1]


def _journal_falso(tmp_path: Path, reinicios: int) -> Path:
    lineas = "\n".join(
        f"datamaq-telemetry.service: Scheduled restart job, restart counter is at {i}." for i in range(1, reinicios + 1)
    )
    script = tmp_path / "journal_falso.sh"
    script.write_text(f"#!/bin/sh\ncat <<'FIN'\n{lineas}\nFIN\n", encoding="utf-8")
    script.chmod(0o755)
    return script


@pytest.mark.parametrize(
    ("reinicios", "alerta"),
    [(0, False), (2, False), (3, True)],
)
def test_monitor_alerta_solo_desde_el_umbral(tmp_path: Path, reinicios: int, alerta: bool) -> None:
    journal = _journal_falso(tmp_path, reinicios)
    entorno = {
        **os.environ,
        "MONITOR_JOURNALCTL": str(journal),
        "MONITOR_LOGGER": "true",  # no escribir en el syslog real desde un test
        "MONITOR_UMBRAL": "3",
    }
    resultado = subprocess.run(["sh", str(MONITOR)], env=entorno, capture_output=True, text=True, check=False)
    if alerta:
        assert resultado.returncode == 1
        assert "ALERTA" in resultado.stderr
    else:
        assert resultado.returncode == 0
        assert "OK" in resultado.stdout
