"""src/infrastructure/produccion/parseo_salida.py — Parseo estricto de la salida de mysql y del entorno remoto.

El entorno remoto solo acepta dos formas: longitud de la clave OTP y APP_ENV. Cualquier otra línea
falla sin reproducir su contenido, para que un valor secreto nunca llegue al reporte.
"""

import re

_NULO = "NULL"
_ENTERO = re.compile(r"-?\d+")
_DECIMAL = re.compile(r"-?\d+\.\d+")
_LINEA_ENTORNO = re.compile(r"(otp_hmac_key_longitud=\d+|app_env=[a-z]{1,20})")


def _convertir(valor: str) -> object:
    if valor == _NULO:
        return None
    if _ENTERO.fullmatch(valor):
        return int(valor)
    if _DECIMAL.fullmatch(valor):
        return float(valor)
    return valor


def parse_tsv(texto: str) -> list[dict[str, object]]:
    """Convierte la salida `mysql --batch` (cabecera + filas TSV) en dicts con claves ordenadas."""
    lineas = [linea for linea in texto.splitlines() if linea != ""]
    if not lineas:
        return []
    cabecera = lineas[0].split("\t")
    filas: list[dict[str, object]] = []
    for linea in lineas[1:]:
        valores = linea.split("\t")
        if len(valores) != len(cabecera):
            raise ValueError(f"fila con {len(valores)} columnas; la cabecera tiene {len(cabecera)}")
        fila = {columna: _convertir(valor) for columna, valor in zip(cabecera, valores, strict=True)}
        filas.append({clave: fila[clave] for clave in sorted(fila)})
    return filas


def parse_entorno(texto: str) -> dict[str, object]:
    """Solo acepta `otp_hmac_key_longitud=<n>` y `app_env=<valor>`. Nunca reproduce una línea inesperada."""
    resultado: dict[str, object] = {"app_env": None, "otp_hmac_key_longitud": None}
    for linea in texto.splitlines():
        if not linea.strip():
            continue
        if not _LINEA_ENTORNO.fullmatch(linea.strip()):
            raise ValueError("salida de entorno remoto inesperada (contenido omitido por seguridad)")
        clave, _, valor = linea.strip().partition("=")
        resultado[clave] = int(valor) if clave == "otp_hmac_key_longitud" else valor
    return {clave: resultado[clave] for clave in sorted(resultado)}
