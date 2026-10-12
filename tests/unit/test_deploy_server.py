"""tests/unit/test_deploy_server.py — Dumps privados y rollback del bloque remoto de scripts/deploy-server.sh (#17).

Corre el heredoc remoto (lo que el deploy ejecuta por ssh en el VPS) con bash real y stubs en el PATH para git, pip,
mysqldump, mysql, sudo y sleep. No toca ninguna base, servicio ni repo: los stubs registran las llamadas en un log.
"""

import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "deploy-server.sh"
INICIO_HEREDOC = "    bash <<'EOF'\n"
FIN_HEREDOC = "\nEOF\n"

STUBS = {
    "git": """
echo "git $*" >> "$LOG"
case "$1" in
    rev-parse) echo "commitanterior" ;;
    pull|merge) [ -n "${GIT_FALLA:-}" ] && exit 1 ;;
esac
exit 0
""",
    "mysqldump": """
echo "mysqldump" >> "$LOG"
if [ -n "${MYSQLDUMP_FALLA:-}" ]; then echo "-- parcial"; exit 2; fi
# Más grande que el buffer de un pipe: el pie se lee bajo pipefail sin abortar por SIGPIPE.
for i in $(seq 1 20000); do echo "INSERT INTO t VALUES ($i,'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx');"; done
[ -z "${SIN_PIE:-}" ] && echo "-- Dump completed on 2026-10-11 21:40:27"
exit 0
""",
    "mysql": 'echo "mysql restaurar" >> "$LOG"; cat > /dev/null',
    "sudo": 'echo "sudo $*" >> "$LOG"',
    "sleep": "exit 0",
}

STUBS_VENV = {
    "pip": """
echo "pip $*" >> "$LOG"
case "$1 ${3:-}" in
    "freeze ") echo "paquete==1.0" ;;
    "install requirements.lock") [ -n "${PIP_FALLA:-}" ] && exit 1 ;;
    *) [ "$1" = install ] && [ -n "${PIP_ROLLBACK_FALLA:-}" ] && exit 1 ;;
esac
exit 0
""",
    "python3": 'if [ -n "${HEALTH_FALLA:-}" ]; then echo 500; else echo 200; fi',
    "alembic": '[ -n "${ALEMBIC_FALLA:-}" ] && exit 1; exit 0',
}


def _heredoc_remoto() -> str:
    texto = SCRIPT.read_text(encoding="utf-8")
    inicio = texto.index(INICIO_HEREDOC) + len(INICIO_HEREDOC)
    return texto[inicio : texto.index(FIN_HEREDOC, inicio)]


def _escribir_stub(ruta: Path, cuerpo: str) -> None:
    ruta.write_text("#!/bin/bash\n" + cuerpo + "\n", encoding="utf-8")
    ruta.chmod(0o755)


class _Deploy:
    def __init__(self, base: Path) -> None:
        self.remoto = base / "remoto"
        self.backups = base / "backups"
        self.log = base / "llamadas.log"
        stubs = base / "stubs"
        venv = self.remoto / ".venv" / "bin"
        for d in (stubs, venv):
            d.mkdir(parents=True)
        for nombre, cuerpo in STUBS.items():
            _escribir_stub(stubs / nombre, cuerpo)
        for nombre, cuerpo in STUBS_VENV.items():
            _escribir_stub(venv / nombre, cuerpo)
        (self.remoto / ".env").write_text("DB_HOST=h\nDB_USER=u\nDB_PASSWORD=p\nDB_NAME=n\n", encoding="utf-8")
        self.log.touch()
        self.env = {
            "PATH": f"{stubs}:/usr/bin:/bin",
            "LOG": str(self.log),
            "DEPLOY_REMOTE_DIR": str(self.remoto),
            "DEPLOY_SERVICE_NAME": "svc",
            "HEALTH_URL": "http://127.0.0.1:1/health",
            "GITHUB_TOKEN": "",
            "GITHUB_REPOSITORY": "",
            "DEPLOY_BACKUP_DIR": str(self.backups),
            "DEPLOY_DEPS_FILE": str(base / "deps.txt"),
        }

    def correr(self, **fallas: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "-c", _heredoc_remoto()],
            env={**self.env, **fallas},
            capture_output=True,
            text=True,
            timeout=60,
        )

    @property
    def llamadas(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines()

    def dumps(self) -> list[Path]:
        return sorted(self.backups.glob("pre_migracion_*.sql.gz"))


@pytest.fixture
def deploy(tmp_path: Path) -> _Deploy:
    return _Deploy(tmp_path)


def _modo(ruta: Path) -> int:
    return stat.S_IMODE(ruta.stat().st_mode)


def test_deploy_feliz_deja_el_directorio_en_700_y_el_dump_en_600(deploy):
    deploy.backups.mkdir(mode=0o755)
    viejo = deploy.backups / "pre_migracion_20260101_000000.sql.gz"
    viejo.write_bytes(b"")
    viejo.chmod(0o644)

    r = deploy.correr()

    assert r.returncode == 0, r.stdout + r.stderr
    assert _modo(deploy.backups) == 0o700
    assert all(_modo(d) == 0o600 for d in deploy.dumps())
    assert len(deploy.dumps()) == 2
    assert "sudo systemctl stop svc" in deploy.llamadas
    assert not any(c.startswith("git reset") for c in deploy.llamadas)


def test_mysqldump_que_falla_aborta_antes_del_stop_y_revierte_el_codigo(deploy):
    """Criterio de cierre de #17: sin pipefail, el `| gzip` tapaba el fallo y se seguía con un dump vacío."""
    r = deploy.correr(MYSQLDUMP_FALLA="1")

    assert r.returncode != 0
    assert not any("systemctl stop" in c for c in deploy.llamadas)
    assert "git reset --hard commitanterior" in deploy.llamadas
    assert "mysql restaurar" not in deploy.llamadas
    assert "Rollback ejecutado" in r.stdout


def test_dump_sin_pie_de_mysqldump_aborta_antes_del_stop_y_se_borra(deploy):
    r = deploy.correr(SIN_PIE="1")

    assert r.returncode != 0
    assert not any("systemctl stop" in c for c in deploy.llamadas)
    assert deploy.dumps() == []
    assert "Dump completed" in r.stdout


def test_fallo_de_pip_revierte_el_codigo_sin_tocar_la_base(deploy):
    r = deploy.correr(PIP_FALLA="1")

    assert r.returncode != 0
    assert "git reset --hard commitanterior" in deploy.llamadas
    assert not any("systemctl" in c for c in deploy.llamadas)
    assert "mysqldump" not in deploy.llamadas


def test_fallo_de_git_revierte_el_codigo(deploy):
    r = deploy.correr(GIT_FALLA="1")

    assert r.returncode != 0
    assert "git reset --hard commitanterior" in deploy.llamadas
    assert not any("systemctl" in c for c in deploy.llamadas)


def test_rollback_que_falla_avisa_incompleto_sin_reentrar(deploy):
    r = deploy.correr(PIP_FALLA="1", PIP_ROLLBACK_FALLA="1")

    assert r.returncode != 0
    assert "ROLLBACK INCOMPLETO" in r.stdout
    assert deploy.llamadas.count("git reset --hard commitanterior") == 1


def test_migracion_que_falla_restaura_base_y_codigo_y_sale_con_error(deploy):
    r = deploy.correr(ALEMBIC_FALLA="1")

    assert r.returncode != 0
    llamadas = deploy.llamadas
    assert "mysql restaurar" in llamadas
    assert "git reset --hard commitanterior" in llamadas
    assert llamadas[-1] == "sudo systemctl start svc"
    assert "Rollback ejecutado (base, código y dependencias)" in r.stdout


def test_health_que_falla_restaura_y_sale_con_error(deploy):
    r = deploy.correr(HEALTH_FALLA="1")

    assert r.returncode != 0
    assert "mysql restaurar" in deploy.llamadas
    assert "git reset --hard commitanterior" in deploy.llamadas


def test_con_token_hace_fetch_a_origin_main_y_merge(deploy):
    r = deploy.correr(GITHUB_TOKEN="tok", GITHUB_REPOSITORY="org/repo")

    assert r.returncode == 0, r.stdout + r.stderr
    assert any("fetch https://github.com/org/repo.git main:refs/remotes/origin/main" in c for c in deploy.llamadas)
    assert "git merge --ff-only origin/main" in deploy.llamadas


@pytest.mark.parametrize("sin", ["GITHUB_TOKEN", "GITHUB_REPOSITORY"])
def test_set_u_tolera_variables_del_fallback_sin_definir(deploy, sin):
    env = dict(deploy.env)
    del env[sin]
    deploy.env = env
    r = deploy.correr()
    assert r.returncode == 0, r.stdout + r.stderr
    assert "git pull --ff-only" in deploy.llamadas
