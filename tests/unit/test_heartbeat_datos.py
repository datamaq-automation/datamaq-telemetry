"""tests/unit/test_heartbeat_datos.py — Heartbeat de datos D2 (scripts/heartbeat_datos.py).

Sin red, sin base y sin secretos: la consulta y el envío del ping se inyectan o se mockean, y la URL es falsa.
"""

import subprocess
import urllib.error
from pathlib import Path

import pytest

from scripts import heartbeat_datos as hb

URL_FALSA = "https://hc-ping.com/00000000-0000-0000-0000-000000000000"


@pytest.fixture
def url_file(tmp_path: Path) -> Path:
    ruta = tmp_path / "heartbeat_url"
    ruta.write_text(URL_FALSA + "\n", encoding="utf-8")
    return ruta


def _env(url_file: Path) -> dict[str, str]:
    return {"HEARTBEAT_PING_URL_FILE": str(url_file), "HEARTBEAT_MYSQL_CNF": "/no/usado.cnf"}


class _Envios:
    """Registra los pings enviados y finge el cliente HTTP."""

    def __init__(self, error: Exception | None = None) -> None:
        self.llamadas: list[tuple[str, bool]] = []
        self._error = error

    def __call__(self, url: str, falla: bool) -> None:
        self.llamadas.append((url, falla))
        if self._error is not None:
            raise self._error


# --- Decisión de frescura -------------------------------------------------------------------------------------------


def test_14_minutos_es_ok():
    assert hb.esta_vivo(14) is True


def test_15_minutos_es_falla():
    assert hb.esta_vivo(15) is False


def test_tabla_vacia_es_falla():
    assert hb.esta_vivo(None) is False


# --- main(): ping OK / falla / tabla vacía / consulta fallida / ping que no sale --------------------------------------


def test_14_minutos_manda_ping_ok_y_sale_0(url_file):
    envios = _Envios()
    codigo = hb.main(_env(url_file), consultar=lambda cnf: 14, enviar=envios)
    assert codigo == 0
    assert envios.llamadas == [(URL_FALSA, False)]


def test_15_minutos_manda_ping_de_falla_y_sale_1(url_file):
    envios = _Envios()
    codigo = hb.main(_env(url_file), consultar=lambda cnf: 15, enviar=envios)
    assert codigo == 1
    assert envios.llamadas == [(URL_FALSA, True)]


def test_tabla_vacia_manda_ping_de_falla(url_file, capsys):
    envios = _Envios()
    codigo = hb.main(_env(url_file), consultar=lambda cnf: None, enviar=envios)
    assert codigo == 1
    assert envios.llamadas == [(URL_FALSA, True)]
    assert "sin filas" in capsys.readouterr().out


def test_consulta_que_falla_manda_ping_de_falla(url_file, capsys):
    def consulta_rota(cnf: str) -> int | None:
        raise hb.ErrorHeartbeat("mysql terminó con código 1")

    envios = _Envios()
    codigo = hb.main(_env(url_file), consultar=consulta_rota, enviar=envios)
    assert codigo == 1
    assert envios.llamadas == [(URL_FALSA, True)]
    assert "consulta fallida" in capsys.readouterr().out


def test_ping_que_no_sale_devuelve_3_sin_imprimir_la_url(url_file, capsys):
    envios = _Envios(error=urllib.error.URLError("sin red"))
    codigo = hb.main(_env(url_file), consultar=lambda cnf: 1, enviar=envios)
    captura = capsys.readouterr()
    assert codigo == 3
    assert "el ping no llegó (URLError)" in captura.err
    assert URL_FALSA not in captura.out + captura.err


def test_la_url_nunca_aparece_en_la_salida_normal(url_file, capsys):
    hb.main(_env(url_file), consultar=lambda cnf: 2, enviar=_Envios())
    captura = capsys.readouterr()
    assert URL_FALSA not in captura.out + captura.err


def test_sin_archivo_de_url_sale_2_y_no_envia_nada(tmp_path, capsys):
    envios = _Envios()
    env = {"HEARTBEAT_PING_URL_FILE": str(tmp_path / "no_existe"), "HEARTBEAT_MYSQL_CNF": "/no/usado.cnf"}
    codigo = hb.main(env, consultar=lambda cnf: 1, enviar=envios)
    assert codigo == 2
    assert envios.llamadas == []
    assert "no se pudo leer la URL" in capsys.readouterr().err


def test_url_que_no_es_https_sale_2(tmp_path):
    ruta = tmp_path / "url"
    ruta.write_text("http://insegura.example/ping\n", encoding="utf-8")
    envios = _Envios()
    codigo = hb.main(_env(ruta), consultar=lambda cnf: 1, enviar=envios)
    assert codigo == 2
    assert envios.llamadas == []


# --- consultar_minutos(): usuario, NULL y código de salida de mysql (subprocess mockeado) ----------------------------


def _mysql_falso(monkeypatch, stdout: str = "", returncode: int = 0) -> list[list[str]]:
    argvs: list[list[str]] = []

    def fake_run(argv, **kwargs):
        argvs.append(argv)
        return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr="")

    monkeypatch.setattr(hb.subprocess, "run", fake_run)
    return argvs


def test_consultar_minutos_devuelve_los_minutos(monkeypatch):
    argvs = _mysql_falso(monkeypatch, stdout="datamaq_ro@127.0.0.1\t14\n")
    assert hb.consultar_minutos("/ruta/cnf") == 14
    assert argvs[0][:2] == ["mysql", "--defaults-file=/ruta/cnf"]
    assert "-p" not in " ".join(argvs[0])  # sin contraseña en argv


def test_consultar_minutos_con_tabla_vacia_devuelve_none(monkeypatch):
    _mysql_falso(monkeypatch, stdout="datamaq_ro@127.0.0.1\tNULL\n")
    assert hb.consultar_minutos("/ruta/cnf") is None


def test_consultar_minutos_aborta_si_el_usuario_no_es_datamaq_ro(monkeypatch):
    _mysql_falso(monkeypatch, stdout="root@localhost\t3\n")
    with pytest.raises(hb.ErrorHeartbeat, match="no como datamaq_ro"):
        hb.consultar_minutos("/ruta/cnf")


def test_consultar_minutos_aborta_si_mysql_falla(monkeypatch):
    _mysql_falso(monkeypatch, stdout="", returncode=1)
    with pytest.raises(hb.ErrorHeartbeat, match="código 1"):
        hb.consultar_minutos("/ruta/cnf")


def test_usuario_incorrecto_en_main_manda_falla_sin_datos(url_file, monkeypatch):
    _mysql_falso(monkeypatch, stdout="root@localhost\t1\n")
    envios = _Envios()
    codigo = hb.main(_env(url_file), enviar=envios)
    assert codigo == 1
    assert envios.llamadas == [(URL_FALSA, True)]


# --- enviar_ping(): convención /fail y status HTTP (urlopen mockeado) -------------------------------------------------


class _Respuesta:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> "_Respuesta":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _urlopen_falso(monkeypatch, status: int = 200) -> list[str]:
    destinos: list[str] = []

    def fake_urlopen(url, timeout):
        destinos.append(url)
        return _Respuesta(status)

    monkeypatch.setattr(hb.urllib.request, "urlopen", fake_urlopen)
    return destinos


def test_ping_ok_va_a_la_url_base(monkeypatch):
    destinos = _urlopen_falso(monkeypatch)
    hb.enviar_ping(URL_FALSA, falla=False)
    assert destinos == [URL_FALSA]


def test_ping_de_falla_agrega_fail(monkeypatch):
    destinos = _urlopen_falso(monkeypatch)
    hb.enviar_ping(URL_FALSA, falla=True)
    assert destinos == [URL_FALSA + "/fail"]


def test_ping_con_status_no_200_es_error(monkeypatch):
    _urlopen_falso(monkeypatch, status=500)
    with pytest.raises(hb.ErrorHeartbeat, match="HTTP 500"):
        hb.enviar_ping(URL_FALSA, falla=False)
