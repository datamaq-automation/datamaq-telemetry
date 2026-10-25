"""scripts/smoke_post_deploy.py — Verificación real post-deploy del endpoint /health/ready."""

import json
import sys
import time
import urllib.error
import urllib.request


def verificar_servicio(
    url: str,
    max_intentos: int = 6,
    espera_segundos: int = 10,
) -> bool:
    """Consulta el endpoint /health/ready del servicio desplegado.

    Reintenta hasta `max_intentos` veces con `espera_segundos` entre reintentos.
    Exige status HTTP 200, status="ready" y database_conectada=true.
    """
    print(f"Iniciando smoke test post-deploy contra: {url}")
    print(f"Configuración: {max_intentos} intentos, {espera_segundos}s entre reintentos.")

    for intento in range(1, max_intentos + 1):
        print(f"[{intento}/{max_intentos}] Consultando {url}...")
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Datamaq-Deploy-SmokeTest/1.0", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                codigo = resp.status
                cuerpo = resp.read().decode("utf-8")
                if codigo == 200:
                    data = json.loads(cuerpo)
                    status = data.get("status")
                    db_ok = data.get("database_conectada")
                    if status == "ready" and db_ok is True:
                        print("✓ Servicio listo: status='ready' y database_conectada=true.")
                        return True
                    print(f"  Respuesta 200 pero servicio no listo: status={status}, database_conectada={db_ok}")
                else:
                    print(f"  Código HTTP no esperado: {codigo}")
        except urllib.error.HTTPError as e:
            cuerpo = e.read().decode("utf-8", errors="replace")
            print(f"  HTTPError {e.code}: {cuerpo}")
        except Exception as e:
            print(f"  Error de conexión/timeout: {e}")

        if intento < max_intentos:
            time.sleep(espera_segundos)

    print(f"✗ Falló la verificación post-deploy tras {max_intentos} intentos.")
    return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 scripts/smoke_post_deploy.py <url> [max_intentos] [espera_segundos]")
        sys.exit(1)

    url_objetivo = sys.argv[1]
    intentos = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    espera = int(sys.argv[3]) if len(sys.argv) > 3 else 10

    if not verificar_servicio(url_objetivo, max_intentos=intentos, espera_segundos=espera):
        sys.exit(1)
