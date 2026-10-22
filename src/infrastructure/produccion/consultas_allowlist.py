"""src/infrastructure/produccion/consultas_allowlist.py — Allowlist cerrada de consultas de producción.

Cada consulta es una constante fija: no hay SQL libre ni interpolación de entrada del usuario.
Toda sentencia debe ser un único SELECT (verificado por `validar_solo_lectura` y por tests).
"""

import re
from collections.abc import Mapping
from types import MappingProxyType

_PALABRAS_PROHIBIDAS: frozenset[str] = frozenset(
    {
        "ALTER",
        "CALL",
        "CREATE",
        "DELETE",
        "DROP",
        "GRANT",
        "INSERT",
        "INTO",
        "LOAD",
        "REPLACE",
        "REVOKE",
        "SET",
        "TRUNCATE",
        "UPDATE",
    }
)

CONSULTAS: Mapping[str, str] = MappingProxyType(
    {
        "thd_i_agregados": """
SELECT 'R' AS fase, device_id,
  COUNT(*) AS n_con_thd,
  SUM(thd_i_r > 15) AS n_gt15,
  SUM(thd_i_r > 100) AS n_gt100,
  SUM(thd_i_r > 15 AND current_r < 1) AS n_gt15_corr_lt1A,
  SUM(thd_i_r > 15 AND current_r < 5) AS n_gt15_corr_lt5A,
  MIN(CASE WHEN thd_i_r > 15 THEN current_r END) AS corr_min_gt15,
  AVG(CASE WHEN thd_i_r > 15 THEN current_r END) AS corr_avg_gt15,
  MAX(CASE WHEN thd_i_r > 15 THEN current_r END) AS corr_max_gt15,
  MIN(recorded_at) AS desde, MAX(recorded_at) AS hasta
FROM telemetry_instantaneous WHERE thd_i_r IS NOT NULL GROUP BY device_id
UNION ALL
SELECT 'S', device_id, COUNT(*), SUM(thd_i_s > 15), SUM(thd_i_s > 100),
  SUM(thd_i_s > 15 AND current_s < 1), SUM(thd_i_s > 15 AND current_s < 5),
  MIN(CASE WHEN thd_i_s > 15 THEN current_s END), AVG(CASE WHEN thd_i_s > 15 THEN current_s END),
  MAX(CASE WHEN thd_i_s > 15 THEN current_s END), MIN(recorded_at), MAX(recorded_at)
FROM telemetry_instantaneous WHERE thd_i_s IS NOT NULL GROUP BY device_id
UNION ALL
SELECT 'T', device_id, COUNT(*), SUM(thd_i_t > 15), SUM(thd_i_t > 100),
  SUM(thd_i_t > 15 AND current_t < 1), SUM(thd_i_t > 15 AND current_t < 5),
  MIN(CASE WHEN thd_i_t > 15 THEN current_t END), AVG(CASE WHEN thd_i_t > 15 THEN current_t END),
  MAX(CASE WHEN thd_i_t > 15 THEN current_t END), MIN(recorded_at), MAX(recorded_at)
FROM telemetry_instantaneous WHERE thd_i_t IS NOT NULL GROUP BY device_id
ORDER BY device_id, fase
""",
        "cobertura_telemetria": """
SELECT device_id,
  COUNT(*) AS total_lecturas,
  COUNT(thd_v_r) AS thd_v_r_no_nulos, COUNT(thd_v_s) AS thd_v_s_no_nulos, COUNT(thd_v_t) AS thd_v_t_no_nulos,
  COUNT(thd_i_r) AS thd_i_r_no_nulos, COUNT(thd_i_s) AS thd_i_s_no_nulos, COUNT(thd_i_t) AS thd_i_t_no_nulos,
  COUNT(current_r) AS current_r_no_nulos, COUNT(current_s) AS current_s_no_nulos, COUNT(current_t) AS current_t_no_nulos,
  MIN(recorded_at) AS desde, MAX(recorded_at) AS hasta
FROM telemetry_instantaneous
GROUP BY device_id
ORDER BY device_id
""",
        "auditoria_cambio_contrasena": """
SELECT estado, DATE(creado_en) AS dia, COUNT(*) AS registros
FROM auditoria_cambio_contrasena
GROUP BY estado, DATE(creado_en)
ORDER BY dia, estado
""",
    }
)


def validar_solo_lectura(sql: str) -> None:
    """Exige una única sentencia SELECT sin palabras de escritura o de sesión. Lanza ValueError si no."""
    texto = sql.strip().rstrip(";").strip()
    if not texto.upper().startswith("SELECT"):
        raise ValueError("la consulta no empieza con SELECT")
    if ";" in texto:
        raise ValueError("la consulta contiene más de una sentencia")
    palabras = set(re.findall(r"[A-Za-z_]+", texto.upper()))
    prohibidas = sorted(palabras & _PALABRAS_PROHIBIDAS)
    if prohibidas:
        raise ValueError(f"la consulta contiene palabras no permitidas: {', '.join(prohibidas)}")
