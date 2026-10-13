"""tests/unit/test_deploy_server.py — Dumps privados y rollback del bloque remoto de scripts/deploy-server.sh (#17).

Corre el heredoc remoto (lo que el deploy ejecuta por ssh en el VPS) con bash real y stubs en el PATH para git, pip,
mysqldump, mysql, sudo y sleep. No toca ninguna base, servicio ni repo: los stubs registran las llamadas en un log.
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "deploy-server.sh"
# git real: el stub de `git` delega `ls-files` aquí, así la normalización de permisos ve los archivos trackeados.
GIT_REAL = shutil.which("git") or "/usr/bin/git"
INICIO_HEREDOC = "    bash <<'EOF'\n"
FIN_HEREDOC = "\nEOF\n"

# La contraseña en argv la ve cualquier usuario local con `ps` (#17): el stub falla si la recibe por ahí. Exige el
# archivo de credenciales como primera opción y registra su modo, si tiene la contraseña y su ruta.
_CREDENCIALES_FUERA_DE_ARGV = """
for a in "$@"; do
    case "$a" in -p*|--password*|-u*|--user*|-h*|--host*) echo "credencial en argv: $a" >> "$LOG"; exit 9 ;; esac
done
case "$1" in --defaults-file=*) cnf=${1#--defaults-file=} ;; *) echo "sin --defaults-file primero" >> "$LOG"; exit 9 ;; esac
echo "cnf $(stat -c %a "$cnf") $(grep -c '^password="p"$' "$cnf")" >> "$LOG"
echo "cnfpath $cnf" >> "$LOG"
"""

STUBS = {
    "git": """
echo "git $*" >> "$LOG"
case "$1" in
    rev-parse) echo "commitanterior" ;;
    ls-files) exec "$GIT_REAL" "$@" ;;
    pull|merge)
        [ -n "${GIT_FALLA:-}" ] && exit 1
        [ -n "${GIT_CREA:-}" ] && echo "x" > nuevo.py
        ;;
esac
exit 0
""",
    "mysqldump": _CREDENCIALES_FUERA_DE_ARGV
    + """
echo "mysqldump" >> "$LOG"
if [ -n "${MYSQLDUMP_FALLA:-}" ]; then echo "-- parcial"; exit 2; fi
# Más grande que el buffer de un pipe: el pie se lee bajo pipefail sin abortar por SIGPIPE.
for i in $(seq 1 20000); do echo "INSERT INTO t VALUES ($i,'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx');"; done
[ -z "${SIN_PIE:-}" ] && echo "-- Dump completed on 2026-10-11 21:40:27"
exit 0
""",
    "mysql": _CREDENCIALES_FUERA_DE_ARGV + 'echo "mysql restaurar" >> "$LOG"; cat > /dev/null',
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
    # HEALTH_FALLA: /health responde 500 siempre. HEALTH_FALLA_PRIMERAS=N: responde 500 los primeros N intentos y
    # después 200 (simula un servicio que se recupera tras el rollback). El contador vive en $LOG.health.
    "python3": """
if [ -n "${HEALTH_FALLA:-}" ]; then echo 500; exit 0; fi
if [ -n "${HEALTH_FALLA_PRIMERAS:-}" ]; then
    n=$(cat "$LOG.health" 2>/dev/null || echo 0)
    echo $((n + 1)) > "$LOG.health"
    [ "$n" -lt "$HEALTH_FALLA_PRIMERAS" ] && { echo 500; exit 0; }
fi
echo 200
""",
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
            "GIT_REAL": GIT_REAL,
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
    assert llamadas[-1] == "sudo systemctl restart svc"
    assert "Rollback ejecutado (base, código y dependencias)" in r.stdout


def test_health_que_falla_restaura_y_sale_con_error(deploy):
    r = deploy.correr(HEALTH_FALLA="1")

    assert r.returncode != 0
    assert "mysql restaurar" in deploy.llamadas
    assert "git reset --hard commitanterior" in deploy.llamadas


def test_health_que_tambien_falla_tras_el_rollback_avisa_rollback_fallido(deploy):
    r = deploy.correr(HEALTH_FALLA="1")

    assert r.returncode != 0
    assert "ROLLBACK FALLIDO: servicio caído" in r.stdout
    assert "Rollback ejecutado" not in r.stdout
    assert deploy.llamadas.count("sudo systemctl restart svc") == 1


def test_health_que_se_recupera_tras_el_rollback_informa_servicio_ok(deploy):
    # 15 = ATTEMPTS del health-check del deploy: falla todo el primer intento y el de después del rollback responde 200.
    r = deploy.correr(HEALTH_FALLA_PRIMERAS="15")

    assert r.returncode != 0
    assert "Rollback ejecutado (base, código y dependencias); el deploy se revirtió y el servicio está OK" in r.stdout
    assert "ROLLBACK FALLIDO" not in r.stdout
    assert deploy.llamadas.count("sudo systemctl restart svc") == 1


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


def test_el_codigo_que_escribe_git_queda_legible_para_el_servicio(deploy):
    """#15: con umask 077 el archivo que escribe git salía 0600 y el servicio (otro usuario) no podía leerlo."""
    r = deploy.correr(GIT_CREA="1")

    assert r.returncode == 0, r.stdout + r.stderr
    assert _modo(deploy.remoto / "nuevo.py") & 0o004


def _repo_con_archivos(deploy: _Deploy, *rutas: str) -> None:
    """Repo git real en el remoto con esas rutas trackeadas (sin commit: basta el índice para ls-files).

    Sin GIT_DIR/GIT_INDEX_FILE del entorno: bajo `git push` el hook los exporta y apuntan al repo real. Sin esto, el
    `git add` del test caía en el índice del worktree.
    """
    entorno = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run([GIT_REAL, "init", "-q"], cwd=deploy.remoto, check=True, env=entorno)
    subprocess.run([GIT_REAL, "add", *rutas], cwd=deploy.remoto, check=True, env=entorno)


def test_normaliza_permisos_de_lectura_antes_de_reiniciar(deploy):
    """Archivos 0600 trackeados de un deploy anterior no pueden bloquear el próximo: se normalizan y el deploy sigue."""
    src = deploy.remoto / "src"
    src.mkdir(mode=0o700)
    codigo = src / "server.py"
    codigo.write_text("x", encoding="utf-8")
    codigo.chmod(0o600)
    _repo_con_archivos(deploy, "src/server.py")

    r = deploy.correr()

    assert r.returncode == 0, r.stdout + r.stderr
    assert _modo(codigo) & 0o004
    assert _modo(src) & 0o005 == 0o005


def test_no_afloja_el_modo_de_env_ni_de_backups_sin_trackear(deploy):
    """Un .env (640) o un .env.bak (600) no trackeados conservan su modo: no pueden quedar legibles para todos."""
    src = deploy.remoto / "src"
    src.mkdir(mode=0o755)
    codigo = src / "server.py"
    codigo.write_text("x", encoding="utf-8")
    codigo.chmod(0o600)
    env = deploy.remoto / ".env"
    env.chmod(0o640)
    bak = deploy.remoto / ".env.bak-20260818-003347"
    bak.write_text("DB_PASSWORD=p\n", encoding="utf-8")
    bak.chmod(0o600)
    _repo_con_archivos(deploy, "src/server.py")

    r = deploy.correr()

    assert r.returncode == 0, r.stdout + r.stderr
    assert _modo(codigo) & 0o004
    assert _modo(env) == 0o640
    assert _modo(bak) == 0o600


def _rutas_cnf(deploy: _Deploy) -> list[Path]:
    return [Path(c.removeprefix("cnfpath ")) for c in deploy.llamadas if c.startswith("cnfpath ")]


def test_la_contrasena_de_la_base_va_en_un_archivo_600_y_no_en_argv(deploy):
    r = deploy.correr()

    assert r.returncode == 0, r.stdout + r.stderr
    assert "cnf 600 1" in deploy.llamadas
    assert not any(c.startswith(("credencial en argv", "sin --defaults-file")) for c in deploy.llamadas)
    assert _rutas_cnf(deploy) and not any(p.exists() for p in _rutas_cnf(deploy))


def test_el_rollback_con_base_tambien_usa_el_archivo_y_lo_borra_al_salir_con_error(deploy):
    """El `exit 1` de abortar_con_rollback tiene que disparar el trap EXIT que borra el archivo."""
    r = deploy.correr(ALEMBIC_FALLA="1")

    assert r.returncode != 0
    assert "mysql restaurar" in deploy.llamadas
    assert deploy.llamadas.count("cnf 600 1") == 2  # mysqldump y mysql
    assert not any(p.exists() for p in _rutas_cnf(deploy))
