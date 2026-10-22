"""tests/unit/test_auditoria_produccion_ssh.py — Adaptador SSH de auditoría (ejecutor falso, sin red)."""

import pytest

from src.infrastructure.produccion.adaptador_ssh import AdaptadorAuditoriaProduccionSsh
from src.infrastructure.produccion.consultas_allowlist import CONSULTAS, validar_solo_lectura
from src.infrastructure.produccion.parseo_salida import parse_entorno, parse_tsv


class _EjecutorFalso:
    def __init__(self, stdout: str = "", error: Exception | None = None) -> None:
        self.stdout = stdout
        self.error = error
        self.llamadas: list[tuple[list[str], str, int]] = []

    def __call__(self, args: list[str], stdin: str, timeout: int) -> str:
        self.llamadas.append((args, stdin, timeout))
        if self.error is not None:
            raise self.error
        return self.stdout


# --- Allowlist y validación de solo lectura ---


@pytest.mark.parametrize("nombre", sorted(CONSULTAS))
def test_toda_consulta_de_la_allowlist_es_solo_select(nombre: str):
    sql = CONSULTAS[nombre]
    assert sql.lstrip().upper().startswith("SELECT")
    validar_solo_lectura(sql)  # no lanza


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM users",
        "UPDATE users SET email = 'x'",
        "SELECT 1; DROP TABLE users",
        "SELECT * INTO OUTFILE '/tmp/x' FROM users",
        "SET GLOBAL max_connections = 1",
        "INSERT INTO users VALUES (1)",
        "  select 1; select 2",
    ],
)
def test_rechaza_sentencias_que_no_son_select_puro(sql: str):
    with pytest.raises(ValueError):
        validar_solo_lectura(sql)


def test_consulta_fuera_de_la_allowlist_no_ejecuta_nada():
    ejecutor = _EjecutorFalso()
    adaptador = AdaptadorAuditoriaProduccionSsh(ejecutor=ejecutor)
    with pytest.raises(ValueError, match="no permitida"):
        adaptador.consultar("DROP TABLE users")
    assert ejecutor.llamadas == []


def test_consulta_nombrada_envia_sql_por_stdin_y_no_en_la_linea_de_comando():
    ejecutor = _EjecutorFalso(stdout="estado\tregistros\ncodigo_solicitado\t3\n")
    adaptador = AdaptadorAuditoriaProduccionSsh(ejecutor=ejecutor)
    adaptador.consultar("auditoria_cambio_contrasena")
    args, stdin, timeout = ejecutor.llamadas[0]
    assert args[0] == "ssh" and "-o" in args and "BatchMode=yes" in args
    assert "auditoria_cambio_contrasena" not in " ".join(args)
    assert "SELECT" not in " ".join(args)
    assert stdin.startswith("SET SESSION TRANSACTION READ ONLY;")
    assert CONSULTAS["auditoria_cambio_contrasena"] in stdin
    assert timeout > 0


def test_host_con_caracteres_raros_se_rechaza():
    with pytest.raises(ValueError):
        AdaptadorAuditoriaProduccionSsh(host="vps; rm -rf /", ejecutor=_EjecutorFalso())


# --- Fallas ruidosas ---


def test_falla_de_ssh_se_propaga_como_error():
    ejecutor = _EjecutorFalso(error=RuntimeError("ssh falló (código 255)"))
    adaptador = AdaptadorAuditoriaProduccionSsh(ejecutor=ejecutor)
    with pytest.raises(RuntimeError, match="ssh falló"):
        adaptador.consultar("thd_i_agregados")


# --- Formato estable ---


def test_parseo_tsv_convierte_tipos_y_ordena_claves():
    texto = "zeta\talfa\tcantidad\tpromedio\n1\tx\t5\t2.5\n2\tNULL\t7\t3\n"
    filas = parse_tsv(texto)
    assert filas == [
        {"alfa": "x", "cantidad": 5, "promedio": 2.5, "zeta": 1},
        {"alfa": None, "cantidad": 7, "promedio": 3, "zeta": 2},
    ]
    assert [list(f.keys()) for f in filas] == [["alfa", "cantidad", "promedio", "zeta"]] * 2


def test_parseo_tsv_vacio_devuelve_lista_vacia():
    assert parse_tsv("") == []


def test_parseo_tsv_fila_con_columnas_de_mas_falla():
    with pytest.raises(ValueError):
        parse_tsv("a\tb\n1\t2\t3\n")


# --- Entorno remoto: nunca valores de claves ---


def test_entorno_remoto_devuelve_longitud_y_app_env():
    ejecutor = _EjecutorFalso(stdout="otp_hmac_key_longitud=43\napp_env=production\n")
    resultado = AdaptadorAuditoriaProduccionSsh(ejecutor=ejecutor).entorno_remoto()
    assert resultado == {"app_env": "production", "otp_hmac_key_longitud": 43}


def test_entorno_remoto_sin_otp_reporta_none():
    resultado = parse_entorno("app_env=production\n")
    assert resultado == {"app_env": "production", "otp_hmac_key_longitud": None}


def test_entorno_remoto_redacta_si_aparece_una_linea_con_valor_secreto():
    secreto = "supersecreto-no-debe-aparecer-123"
    with pytest.raises(ValueError) as excinfo:
        parse_entorno(f"OTP_HMAC_KEY={secreto}\n")
    assert secreto not in str(excinfo.value)


def test_entorno_remoto_rechaza_app_env_con_contenido_inesperado():
    with pytest.raises(ValueError):
        parse_entorno("app_env=production; cat /etc/shadow\n")


def test_comando_de_entorno_no_imprime_el_contenido_de_las_claves():
    from src.infrastructure.produccion import adaptador_ssh

    comando = adaptador_ssh._COMANDO_ENTORNO
    assert "length(v)" in comando
    assert 'print "OTP_HMAC_KEY' not in comando and "print $0" not in comando
